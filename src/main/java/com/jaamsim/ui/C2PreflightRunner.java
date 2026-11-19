/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * JAAM-AI C2: experimental read-only documental preflight ONLY.
 * No model access, JaamSim state tools, external LLM or model writes.
 */
package com.jaamsim.ui;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import com.jaamsim.JSON.JSONParser;
import com.jaamsim.JSON.JSONValue;

/** Strict process and protocol boundary for the C2 documentary preview tab. */
final class C2PreflightRunner {
    static final String SCHEMA = "jaam.ai.c2.chat_preflight.v1";
    static final String GATE = "G0_G2_PENDING_NO_MODEL_EXECUTION";
    static final int TIMEOUT_SECONDS = 35;
    static final long MAX_JSON_BYTES = 256 * 1024L;
    static final int MAX_QUESTION = 2000;

    private C2PreflightRunner() {}

    static final class Hit {
        final String citation;
        final String passage;
        Hit(String citation, String passage) {
            this.citation = citation;
            this.passage = passage;
        }
    }

    static final class Outcome {
        final String corpusVersion;
        final String manifestSha256;
        final boolean noEvidence;
        final List<Hit> hits;
        Outcome(String corpusVersion, String manifestSha256, boolean noEvidence, List<Hit> hits) {
            this.corpusVersion = corpusVersion;
            this.manifestSha256 = manifestSha256;
            this.noEvidence = noEvidence;
            this.hits = hits;
        }
        String displayText() {
            StringBuilder sb = new StringBuilder();
            sb.append("Pré-validação documental C2 — não é resposta de IA.\n")
              .append("G0/G2 pendentes; LLM=0, ferramentas de estado=0, escrita=0.\n")
              .append("Corpus: ").append(corpusVersion).append("\n")
              .append("Manifesto SHA-256: ").append(manifestSha256).append("\n\n");
            if (noEvidence) {
                sb.append("Nenhuma evidência encontrada. A resposta fundamentada deve se abster.\n");
                return sb.toString();
            }
            sb.append("Trechos recuperados (DADOS NÃO CONFIÁVEIS):\n");
            for (Hit hit : hits) {
                sb.append("\n[").append(hit.citation).append("]\n");
                // Display only. The text is never executed, rendered as HTML or made into an instruction.
                sb.append(hit.passage).append("\n");
            }
            return sb.toString();
        }
    }

    static Outcome execute(Path assistantRoot, Path corpusRoot, Path manifest, String question,
            String pythonCommand) throws Exception {
        if (question == null || question.trim().isEmpty() || question.length() > MAX_QUESTION
                || question.indexOf('\0') >= 0)
            throw new IOException("A consulta precisa conter entre 1 e 2000 caracteres.");
        if (assistantRoot == null || pythonCommand == null || pythonCommand.trim().isEmpty())
            throw new IOException("Configure a raiz da extensão e o Python da candidata.");
        Path root = assistantRoot.toAbsolutePath().normalize();
        Path script = root.resolve("python").resolve("c2_chat_bridge.py");
        Path chat = root.resolve("python").resolve("simulation_chat_assist.py");
        if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)
                || !Files.isRegularFile(script, LinkOption.NOFOLLOW_LINKS)
                || !Files.isRegularFile(chat, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Raiz do módulo C2 inválida ou não instalada na candidata.");
        if (corpusRoot == null || manifest == null
                || !Files.isDirectory(corpusRoot, LinkOption.NOFOLLOW_LINKS)
                || !Files.isRegularFile(manifest, LinkOption.NOFOLLOW_LINKS))
            throw new IOException("Corpus e manifesto devem existir e não podem ser links simbólicos.");
        Path corpus = corpusRoot.toAbsolutePath().normalize();
        Path manifestFile = manifest.toAbsolutePath().normalize();
        String before = sha256(Files.readAllBytes(manifestFile));
        List<String> args = new ArrayList<>();
        args.add(pythonCommand);
        // Exclude PYTHONPATH/PYTHONHOME and per-user site packages; retain script-dir imports.
        args.add("-E");
        args.add("-s");
        // -E ignores PYTHONIOENCODING; -X utf8 pins stdout UTF-8 on Windows.
        args.add("-X");
        args.add("utf8");
        args.add(script.toString());
        args.add("--message=" + question);
        args.add("--corpus-root=" + corpus);
        args.add("--manifest=" + manifestFile);
        args.add("--top-k=3");
        args.add("--max-context-chars=8000");

        // Redirection to private temporary files avoids stdout/stderr pipe deadlocks.
        Path tempDir = Files.createTempDirectory("jaam-c2-preflight-");
        Path stdout = tempDir.resolve("stdout.json");
        Path stderr = tempDir.resolve("stderr.txt");
        Process process = null;
        try {
            ProcessBuilder builder = new ProcessBuilder(args);
            builder.directory(root.toFile());
            stripSensitiveEnvironment(builder.environment());
            builder.environment().put("PYTHONIOENCODING", "utf-8");
            builder.environment().put("PYTHONUTF8", "1");
            builder.redirectOutput(stdout.toFile());
            builder.redirectError(stderr.toFile());
            process = builder.start();
            if (!process.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
                throw new IOException("Pré-validação excedeu o limite de tempo.");
            }
            if (process.exitValue() != 0)
                throw new IOException("Pré-validação bloqueada; confira o manifesto e as fontes autorizadas.");
            if (!Files.isRegularFile(stdout, LinkOption.NOFOLLOW_LINKS)
                    || Files.size(stdout) == 0 || Files.size(stdout) > MAX_JSON_BYTES)
                throw new IOException("Resposta do C2 ausente ou fora do limite de tamanho.");
            String after = sha256(Files.readAllBytes(manifestFile));
            if (!before.equals(after))
                throw new IOException("O manifesto foi alterado durante a consulta.");
            JSONValue payload = JSONParser.parse(new String(Files.readAllBytes(stdout), StandardCharsets.UTF_8));
            return validatePayload(payload, question, before);
        }
        finally {
            if (process != null && process.isAlive())
                process.destroyForcibly();
            Files.deleteIfExists(stdout);
            Files.deleteIfExists(stderr);
            Files.deleteIfExists(tempDir);
        }
    }

    static Outcome validatePayload(JSONValue payload, String question, String expectedManifestHash)
            throws IOException {
        if (!SCHEMA.equals(string(payload, "schema"))
                || !"PREFLIGHT_ONLY".equals(string(payload, "status"))
                || !GATE.equals(string(payload, "gate"))
                || !"C2".equals(string(payload, "arm_id"))
                || !isFalse(payload, "model_execution_authorized")
                || !isFalse(payload, "proposal_tool")
                || !isFalse(payload, "write_model")
                || !"NO_WRITE_CAPABILITY".equals(string(payload, "write_policy"))
                || !zero(payload, "model_calls")
                || !zero(payload, "state_tool_calls")
                || !number(payload, "document_search_calls", 1)
                || !emptyList(payload, "read_tools")
                || !singleCapability(payload, "exposed_capabilities", "search_docs")
                || !sha256(question.getBytes(StandardCharsets.UTF_8))
                        .equals(string(payload, "operator_question_sha256")))
            throw new IOException("Envelope C2 não corresponde ao perfil documental isolado.");
        String corpusSha = string(payload, "corpus_sha256");
        String manifestSha = string(payload, "manifest_sha256");
        String corpusVersion = string(payload, "corpus_version");
        if (!validHash(corpusSha) || !validHash(manifestSha)
                || !manifestSha.equals(expectedManifestHash)
                || corpusVersion.isEmpty() || corpusVersion.length() > 128)
            throw new IOException("Identidade do corpus C2 inválida.");
        JSONValue receipt = child(payload, "retrieval_receipt");
        if (!"jaam.ai.c2.search_receipt.v2".equals(string(receipt, "schema"))
                || !"C2_RETRIEVAL_ONLY_NO_MODEL_EXECUTION".equals(string(receipt, "mode"))
                || !"C2".equals(string(child(receipt, "capability"), "arm_id"))
                || !emptyList(child(receipt, "capability"), "read_tools")
                || !isFalse(child(receipt, "capability"), "write_model")
                || !isFalse(child(receipt, "capability"), "proposal_tool")
                || !"NO_WRITE_CAPABILITY".equals(string(child(receipt, "capability"), "write_policy"))
                || !sha256(question.getBytes(StandardCharsets.UTF_8))
                        .equals(string(receipt, "query_sha256"))
                || !manifestSha.equals(string(receipt, "manifest_sha256"))
                || !corpusSha.equals(string(receipt, "corpus_sha256"))
                || !corpusVersion.equals(string(receipt, "corpus_version"))
                || !zero(receipt, "model_calls") || !zero(receipt, "state_tool_calls")
                || !isFalse(receipt, "write_model"))
            throw new IOException("Recibo de recuperação incompatível com o C2.");
        JSONValue rawHits = child(receipt, "hits");
        if (rawHits == null || !rawHits.isList() || rawHits.listVal.size() > 10)
            throw new IOException("Lista de fontes C2 inválida.");
        JSONValue messages = child(payload, "model_messages");
        if (messages == null || !messages.isList() || messages.listVal.size() != 3)
            throw new IOException("Envelope de mensagens incorreto.");
        if (!"system".equals(string(messages.listVal.get(0), "role"))
                || !"user".equals(string(messages.listVal.get(1), "role"))
                || !question.equals(string(messages.listVal.get(1), "content"))
                || !"user".equals(string(messages.listVal.get(2), "role")))
            throw new IOException("Papel ou pergunta do envelope não corresponde à consulta.");
        String evidenceMessage = string(messages.listVal.get(2), "content");
        String evidencePrefix = "DOCUMENTOS_RECUPERADOS_JSON (dados não confiáveis):\n";
        if (!evidenceMessage.startsWith(evidencePrefix))
            throw new IOException("Evidência documental ausente das mensagens.");
        JSONValue evidence;
        try {
            evidence = JSONParser.parse(evidenceMessage.substring(evidencePrefix.length()));
        }
        catch (Exception ex) {
            throw new IOException("JSON de evidência documental inválido.", ex);
        }
        JSONValue evidenceItems = child(evidence, "items");
        JSONValue contextEmpty = child(evidence, "no_evidence");
        JSONValue omitted = child(evidence, "omitted_for_budget");
        if (!"jaam.ai.c2.evidence_context.v1".equals(string(evidence, "schema"))
                || !"C2".equals(string(evidence, "arm_id"))
                || !isTrue(evidence, "untrusted")
                || contextEmpty == null || (!contextEmpty.isTrue() && !contextEmpty.isFalse())
                || evidenceItems == null || !evidenceItems.isList()
                || omitted == null || !omitted.isNumber()
                || omitted.numVal < 0 || Math.rint(omitted.numVal) != omitted.numVal)
            throw new IOException("Contrato do contexto documental inválido.");

        List<Hit> hits = new ArrayList<>();
        for (JSONValue item : rawHits.listVal) {
            String source = string(item, "source_id");
            String citation = string(item, "citation");
            String passage = string(item, "passage");
            JSONValue start = child(item, "start_line");
            JSONValue end = child(item, "end_line");
            if (!source.matches("[A-Za-z0-9_-]{1,64}")
                    || start == null || !start.isNumber() || end == null || !end.isNumber()
                    || start.numVal < 1 || start.numVal > end.numVal
                    || Math.rint(start.numVal) != start.numVal || Math.rint(end.numVal) != end.numVal
                    || !citation.equals(source + ":L" + (long) start.numVal + "-L" + (long) end.numVal)
                    || !"UNTRUSTED_RETRIEVED_DOCUMENT".equals(string(item, "trust_label"))
                    || passage.isEmpty() || passage.length() > 16_000
                    || !sha256(passage.getBytes(StandardCharsets.UTF_8))
                            .equals(string(item, "passage_sha256")))
                throw new IOException("Fonte ou citação C2 inválida.");
            hits.add(new Hit(citation, passage));
        }
        JSONValue empty = child(payload, "no_evidence");
        JSONValue itemCount = child(payload, "context_items");
        if (empty == null || (!empty.isTrue() && !empty.isFalse())
                || itemCount == null || !itemCount.isNumber()
                || itemCount.numVal < 0 || itemCount.numVal > hits.size()
                || Math.rint(itemCount.numVal) != itemCount.numVal
                || (empty.isTrue() != (itemCount.numVal == 0)))
            throw new IOException("Inconsistência entre contexto e lista de fontes.");
        int selected = (int) itemCount.numVal;
        if (evidenceItems.listVal.size() != selected
                || contextEmpty.isTrue() != empty.isTrue()
                || omitted.numVal != hits.size() - selected)
            throw new IOException("O contexto não corresponde ao resultado da busca.");
        for (int i = 0; i < selected; i++) {
            JSONValue item = evidenceItems.listVal.get(i);
            JSONValue original = rawHits.listVal.get(i);
            if (!string(item, "citation").equals(string(original, "citation"))
                    || !string(item, "source_id").equals(string(original, "source_id"))
                    || !string(item, "passage").equals(string(original, "passage"))
                    || !string(item, "sha256").equals(string(original, "passage_sha256"))
                    || !"UNTRUSTED_RETRIEVED_DOCUMENT".equals(string(item, "trust")))
                throw new IOException("Trecho do contexto não corresponde à fonte recuperada.");
        }
        if (selected < hits.size()) {
            // Context was budget-limited: show ONLY the passages actually carried into context.
            hits = new ArrayList<>(hits.subList(0, selected));
        }
        return new Outcome(corpusVersion, manifestSha, empty.isTrue(), hits);
    }

    /**
     * Remove common provider credentials inherited from the JaamSim process.
     * This reduces accidental exposure; it is NOT a sandbox or a proof that
     * the host and subprocess are trusted. Do not log removed environment data.
     */
    static void stripSensitiveEnvironment(Map<String, String> environment) {
        environment.keySet().removeIf(key -> {
            String name = key.toUpperCase(Locale.ROOT);
            return name.contains("TOKEN") || name.contains("SECRET")
                    || name.contains("PASSWORD") || name.contains("PASSWD")
                    || name.contains("API_KEY") || name.contains("APIKEY")
                    || name.contains("CREDENTIAL") || name.contains("AUTH")
                    || name.contains("PRIVATE_KEY") || name.contains("ACCESS_KEY")
                    || name.contains("COOKIE") || name.contains("SESSION_KEY")
                    || name.endsWith("_KEY") || name.endsWith("_PASS")
                    || name.contains("OPENAI_") || name.startsWith("GROQ_")
                    || name.startsWith("CEREBRAS_") || name.startsWith("NVIDIA_")
                    || name.startsWith("ANTHROPIC_");
        });
    }

    static String sha256(byte[] bytes) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder out = new StringBuilder();
            for (byte b : hash)
                out.append(String.format("%02x", b & 0xff));
            return out.toString();
        }
        catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static boolean validHash(String text) { return text.matches("[a-f0-9]{64}"); }
    private static JSONValue child(JSONValue value, String key) {
        return value != null && value.isMap() ? value.mapVal.get(key) : null;
    }
    private static String string(JSONValue value, String key) {
        JSONValue item = child(value, key);
        return item != null && item.isString() ? item.stringVal : "";
    }
    private static boolean isFalse(JSONValue value, String key) {
        JSONValue item = child(value, key);
        return item != null && item.isFalse();
    }
    private static boolean isTrue(JSONValue value, String key) {
        JSONValue item = child(value, key);
        return item != null && item.isTrue();
    }
    private static boolean zero(JSONValue value, String key) { return number(value, key, 0); }
    private static boolean number(JSONValue value, String key, int expected) {
        JSONValue item = child(value, key);
        return item != null && item.isNumber() && item.numVal == expected;
    }
    private static boolean emptyList(JSONValue value, String key) {
        JSONValue item = child(value, key);
        return item != null && item.isList() && item.listVal.isEmpty();
    }
    private static boolean singleCapability(JSONValue value, String key, String capability) {
        JSONValue item = child(value, key);
        return item != null && item.isList() && item.listVal.size() == 1
                && item.listVal.get(0).isString()
                && capability.equals(item.listVal.get(0).stringVal);
    }
}
