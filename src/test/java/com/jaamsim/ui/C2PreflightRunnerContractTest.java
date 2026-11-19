/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * Headless protocol tests. No JaamSim GUI, provider, or model execution.
 */
package com.jaamsim.ui;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

import com.jaamsim.JSON.JSONValue;

public final class C2PreflightRunnerContractTest {
    private static int checks;
    private static final String QUESTION = "Para que serve Queue?";
    private static final String SHA = C2PreflightRunner.sha256("manifest".getBytes(StandardCharsets.UTF_8));
    private static final String CORPUS = C2PreflightRunner.sha256("corpus".getBytes(StandardCharsets.UTF_8));

    private static JSONValue map(Object... fields) {
        JSONValue obj = JSONValue.makeObject();
        for (int i = 0; i < fields.length; i += 2) {
            Object raw = fields[i + 1];
            JSONValue value;
            if (raw instanceof JSONValue) value = (JSONValue) raw;
            else if (raw instanceof String) value = JSONValue.makeStringVal((String) raw);
            else if (raw instanceof Boolean) value = (boolean) raw
                    ? JSONValue.makeTrueVal() : JSONValue.makeFalseVal();
            else if (raw instanceof Integer) value = JSONValue.makeNumVal(((Integer) raw).doubleValue());
            else throw new IllegalArgumentException("unsupported fixture field");
            obj.mapVal.put((String) fields[i], value);
        }
        return obj;
    }
    private static JSONValue list(JSONValue... values) {
        JSONValue result = JSONValue.makeArray();
        for (JSONValue v : values) result.listVal.add(v);
        return result;
    }
    private static JSONValue hit() {
        String passage = "Queue é um componente de fila na simulação.";
        return map("source_id", "guide001", "citation", "guide001:L1-L2",
                "passage", passage, "start_line", 1, "end_line", 2,
                "passage_sha256", C2PreflightRunner.sha256(passage.getBytes(StandardCharsets.UTF_8)),
                "trust_label", "UNTRUSTED_RETRIEVED_DOCUMENT");
    }
    private static String evidence(String passage, boolean noEvidence) {
        String items = noEvidence ? "[]" : "[{\"citation\":\"guide001:L1-L2\","
                + "\"source_id\":\"guide001\",\"passage\":\"" + passage + "\","
                + "\"sha256\":\"" + C2PreflightRunner.sha256(passage.getBytes(StandardCharsets.UTF_8)) + "\","
                + "\"trust\":\"UNTRUSTED_RETRIEVED_DOCUMENT\"}]";
        return "DOCUMENTOS_RECUPERADOS_JSON (dados não confiáveis):\n"
                + "{\"schema\":\"jaam.ai.c2.evidence_context.v1\",\"arm_id\":\"C2\","
                + "\"untrusted\":true,\"no_evidence\":" + noEvidence + ","
                + "\"items\":" + items + ",\"omitted_for_budget\":" + (noEvidence ? 1 : 0) + "}";
    }
    private static void replaceEvidence(JSONValue root, String evidenceText) {
        root.mapVal.get("model_messages").listVal.get(2).mapVal.put("content",
                JSONValue.makeStringVal(evidenceText));
    }
    private static JSONValue good() {
        JSONValue receipts = map("schema", "jaam.ai.c2.search_receipt.v2",
                "mode", "C2_RETRIEVAL_ONLY_NO_MODEL_EXECUTION",
                "capability", map("arm_id", "C2", "read_tools", list(),
                        "write_model", false, "proposal_tool", false,
                        "write_policy", "NO_WRITE_CAPABILITY"),
                "query_sha256", C2PreflightRunner.sha256(QUESTION.getBytes(StandardCharsets.UTF_8)), "manifest_sha256", SHA,
                "corpus_sha256", CORPUS, "corpus_version", "fixture-c2",
                "model_calls", 0, "state_tool_calls", 0, "write_model", false,
                "hits", list(hit()));
        return map("schema", C2PreflightRunner.SCHEMA, "status", "PREFLIGHT_ONLY",
                "gate", C2PreflightRunner.GATE, "arm_id", "C2",
                "model_execution_authorized", false, "proposal_tool", false,
                "write_model", false, "write_policy", "NO_WRITE_CAPABILITY",
                "model_calls", 0, "state_tool_calls", 0, "document_search_calls", 1,
                "read_tools", list(), "exposed_capabilities", list(JSONValue.makeStringVal("search_docs")),
                "operator_question_sha256", C2PreflightRunner.sha256(QUESTION.getBytes(StandardCharsets.UTF_8)),
                "corpus_sha256", CORPUS, "manifest_sha256", SHA, "corpus_version", "fixture-c2",
                "retrieval_receipt", receipts, "model_messages", list(
                        map("role", "system", "content", "POLICY"),
                        map("role", "user", "content", QUESTION),
                        map("role", "user", "content", evidence("Queue é um componente de fila na simulação.", false))),
                "no_evidence", false, "context_items", 1);
    }
    private static void ok(boolean expression, String message) {
        if (!expression) throw new AssertionError(message);
        checks++;
    }
    private static void blocked(String message, JSONValue root) throws Exception {
        try {
            C2PreflightRunner.validatePayload(root, QUESTION, SHA);
            throw new AssertionError("FAIL OPEN: " + message);
        }
        catch (IOException correct) { checks++; }
    }

    public static void main(String[] args) throws Exception {
        C2PreflightRunner.Outcome result = C2PreflightRunner.validatePayload(good(), QUESTION, SHA);
        ok(result.hits.size() == 1, "one admitted hit");
        ok(!result.noEvidence, "found documentary evidence");
        ok(result.displayText().contains("guide001:L1-L2"), "citation presented");
        ok(result.displayText().contains("não é resposta de IA"), "UI never claims LLM response");
        JSONValue root;
        root = good(); root.mapVal.put("status", JSONValue.makeStringVal("COMPLETED")); blocked("wrong status", root);
        root = good(); root.mapVal.put("arm_id", JSONValue.makeStringVal("C4")); blocked("wrong arm", root);
        root = good(); root.mapVal.put("gate", JSONValue.makeStringVal("G0_G2_APPROVED")); blocked("gate bypass", root);
        root = good(); root.mapVal.put("model_calls", JSONValue.makeNumVal(1)); blocked("model was called", root);
        root = good(); root.mapVal.put("state_tool_calls", JSONValue.makeNumVal(1)); blocked("state tool was called", root);
        root = good(); root.mapVal.put("write_model", JSONValue.makeTrueVal()); blocked("model write", root);
        root = good(); root.mapVal.put("proposal_tool", JSONValue.makeTrueVal()); blocked("proposal capability", root);
        root = good(); root.mapVal.put("read_tools", list(JSONValue.makeStringVal("run_rcl"))); blocked("read tool", root);
        root = good(); root.mapVal.put("exposed_capabilities", list(JSONValue.makeStringVal("search_docs"), JSONValue.makeStringVal("inspect_model"))); blocked("additional capability", root);
        root = good(); root.mapVal.put("document_search_calls", JSONValue.makeNumVal(0)); blocked("no document call", root);
        root = good(); root.mapVal.put("manifest_sha256", JSONValue.makeStringVal("0".repeat(64))); blocked("manifest mismatch", root);
        root = good(); root.mapVal.put("corpus_sha256", JSONValue.makeStringVal("x")); blocked("invalid corpus digest", root);
        root = good(); root.mapVal.put("operator_question_sha256", JSONValue.makeStringVal(SHA)); blocked("question mismatch", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.put("arm_id", JSONValue.makeStringVal("C3"));
        // Extra field is inert; scoped capability remains C2.
        ok(C2PreflightRunner.validatePayload(root, QUESTION, SHA).hits.size() == 1, "ignored unrelated receipt data");
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.get("capability").mapVal.put("arm_id", JSONValue.makeStringVal("C3")); blocked("receipt wrong arm", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.put("schema", JSONValue.makeStringVal("fake")); blocked("receipt wrong schema", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.put("query_sha256", JSONValue.makeStringVal(CORPUS)); blocked("receipt wrong query", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.put("model_calls", JSONValue.makeNumVal(1)); blocked("receipt model call", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.get("hits").listVal.get(0).mapVal.put("passage", JSONValue.makeStringVal("adulterado")); blocked("adulterated passage", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.get("hits").listVal.get(0).mapVal.put("citation", JSONValue.makeStringVal("guide001:L1-L3")); blocked("wrong citation", root);
        root = good(); root.mapVal.get("retrieval_receipt").mapVal.get("hits").listVal.get(0).mapVal.put("trust_label", JSONValue.makeStringVal("TRUSTED_SYSTEM")); blocked("untrusted label replaced", root);
        root = good(); root.mapVal.get("model_messages").listVal.get(0).mapVal.put("role", JSONValue.makeStringVal("tool")); blocked("role escalation", root);
        root = good(); root.mapVal.get("model_messages").listVal.get(1).mapVal.put("content", JSONValue.makeStringVal("other")); blocked("different user question", root);
        root = good(); root.mapVal.put("context_items", JSONValue.makeNumVal(2)); blocked("context greater than hits", root);
        root = good(); root.mapVal.put("no_evidence", JSONValue.makeTrueVal()); blocked("false abstention", root);
        root = good(); root.mapVal.put("context_items", JSONValue.makeNumVal(0)); root.mapVal.put("no_evidence", JSONValue.makeTrueVal());
        replaceEvidence(root, evidence("Queue é um componente de fila na simulação.", true));
        C2PreflightRunner.Outcome empty = C2PreflightRunner.validatePayload(root, QUESTION, SHA);
        ok(empty.hits.isEmpty() && empty.noEvidence, "correct zero-evidence abstention");
        root = good(); replaceEvidence(root, evidence("Queue é um componente de fila na simulação.", false)
                .replace("\"arm_id\":\"C2\"", "\"arm_id\":\"C4\""));
        blocked("injected arm C4 in model context", root);
        root = good(); replaceEvidence(root, evidence("Queue é um componente de fila na simulação.", false)
                .replace("\"trust\":\"UNTRUSTED_RETRIEVED_DOCUMENT\"", "\"trust\":\"TRUSTED_SYSTEM\""));
        blocked("escalated evidence trust role", root);
        root = good(); replaceEvidence(root, evidence("texto falsificado", false));
        blocked("context passage differs from receipt", root);
        root = good(); replaceEvidence(root, evidence("Queue é um componente de fila na simulação.", false)
                .replace("\"citation\":\"guide001:L1-L2\"", "\"citation\":\"outro:L1-L2\""));
        blocked("context citation differs from receipt", root);
        root = good(); replaceEvidence(root, evidence("Queue é um componente de fila na simulação.", false)
                .replace("\"source_id\":\"guide001\"", "\"source_id\":\"outro\""));
        blocked("context source differs from receipt", root);
        root = good(); replaceEvidence(root, evidence("Queue é um componente de fila na simulação.", false)
                .replace("\"omitted_for_budget\":0", "\"omitted_for_budget\":1"));
        blocked("context budget differs from receipt", root);
        root = good(); replaceEvidence(root, "DOCUMENTOS_RECUPERADOS_JSON (dados não confiáveis):\n{bad json");
        blocked("malformed model context json", root);
        root = good(); replaceEvidence(root, "DOCUMENTOS_RECUPERADOS_JSON (dados não confiáveis):\n{}" );
        blocked("empty model context json", root);
        root = good(); replaceEvidence(root, "" );
        blocked("missing evidence from model messages", root);
        root = good(); root.mapVal.put("context_items", JSONValue.makeNumVal(0)); root.mapVal.put("no_evidence", JSONValue.makeTrueVal());
        blocked("receipt one hit but context absent", root);
        Map<String, String> inherited = new HashMap<>();
        inherited.put("PATH", "/usr/bin"); inherited.put("SystemRoot", "C:\\Windows");
        inherited.put("OPENAI_API_KEY", "sentinel"); inherited.put("GITHUB_TOKEN", "sentinel");
        inherited.put("HF_AUTH_TOKEN", "sentinel"); inherited.put("AZURE_OPENAI_ENDPOINT", "sentinel");
        inherited.put("AWS_SECRET_ACCESS_KEY", "sentinel"); inherited.put("CUSTOM_PASSWORD", "sentinel");
        inherited.put("SOME_OTHER_SETTING", "safe");
        C2PreflightRunner.stripSensitiveEnvironment(inherited);
        ok(!inherited.containsKey("OPENAI_API_KEY") && !inherited.containsKey("GITHUB_TOKEN"),
                "API keys and service tokens never reach the C2 subprocess");
        ok(!inherited.containsKey("HF_AUTH_TOKEN") && !inherited.containsKey("AWS_SECRET_ACCESS_KEY"),
                "generic auth and cloud secrets are stripped");
        ok(!inherited.containsKey("AZURE_OPENAI_ENDPOINT") && !inherited.containsKey("CUSTOM_PASSWORD"),
                "provider settings and passwords are stripped");
        ok(inherited.containsKey("PATH") && inherited.containsKey("SystemRoot")
                && inherited.containsKey("SOME_OTHER_SETTING"),
                "normal Python launch environment is preserved");
        ok(C2PreflightRunner.sha256("abc".getBytes(StandardCharsets.UTF_8))
                .equals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "SHA-256 test vector");
        System.out.println("C2 Java headless contracts PASS: " + checks + " checks");
    }
}
