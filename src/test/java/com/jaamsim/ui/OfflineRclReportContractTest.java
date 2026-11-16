/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * Headless contract regression for JaamSim's offline RCL report provenance.
 * No JFrame, simulation engine, Python interpreter, network or CFG execution.
 */
package com.jaamsim.ui;

import java.lang.reflect.Method;
import java.io.File;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class OfflineRclReportContractTest {

	private static int checks = 0;

	private static String escape(String raw) {
		return raw.replace("\\", "\\\\").replace("\"", "\\\"");
	}

	private static String report(Path source, String model, boolean onlineApi, boolean llm) {
		String file = escape(source.toAbsolutePath().normalize().toString());
		return "{\"mode\":\"offline_deterministico\",\"input_type\":\"cfg\","
				+ "\"input_file\":\"" + file + "\",\"analysis\":{\"model_id\":\""
				+ escape(model) + "\"},\"ai_usage\":{\"internet_api\":" + onlineApi
				+ ",\"llm_online\":false,\"local_ai\":false},"
				+ "\"llm_online_assist\":{\"enabled\":" + llm + "}}";
	}

	private static String statuses(Path source, String model) {
		String file = escape(source.toAbsolutePath().normalize().toString());
		return "{\"model_id\":\"" + escape(model)
				+ "\",\"input_file\":\"" + file
				+ "\",\"suggestions\":[]}";
	}

	private static String validate(Method verifier, Path report, Path cfg, Path assistantRoot)
			throws Exception {
		return (String) verifier.invoke(null, report, cfg, "demo", assistantRoot);
	}

	private static void expectValid(Method verifier, Path report, Path cfg, Path assistantRoot)
			throws Exception {
		String failure = validate(verifier, report, cfg, assistantRoot);
		if (failure != null)
			throw new AssertionError("Valid offline report rejected: " + failure);
		checks++;
	}

	private static void expectBlocked(Method verifier, Path report, Path cfg, Path assistantRoot)
			throws Exception {
		String failure = validate(verifier, report, cfg, assistantRoot);
		if (failure == null || failure.trim().isEmpty())
			throw new AssertionError("Invalid or unrelated RCL report accepted");
		checks++;
	}


	private static String sha256(Path file) throws Exception {
		return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
				.digest(Files.readAllBytes(file)));
	}

	private static String runtime(Path executable, Path script) throws Exception {
		return "{\"schema\":\"jaam.ai.python_runtime.v1\","
				+ "\"evidence_level\":\"self_reported_no_external_attestation\","
				+ "\"python_executable\":\"" + escape(executable.toRealPath().toString()) + "\","
				+ "\"python_executable_sha256\":\"" + sha256(executable) + "\","
				+ "\"python_version\":\"3.11.9\","
				+ "\"python_implementation\":\"CPython\","
				+ "\"entry_script\":\"" + escape(script.toRealPath().toString()) + "\","
				+ "\"entry_script_sha256\":\"" + sha256(script) + "\"}";
	}

	private static String addRuntime(String json, String runtime) {
		return json.substring(0, json.length() - 1) + ",\"python_runtime\":" + runtime + "}";
	}

	private static String receipt(Path cfg, String cfgSha, String reportSha, boolean unchanged) {
		return "{\"schema\":\"jaam.ai.offline_review.receipt.v1\","
				+ "\"source_cfg\":\"" + escape(cfg.toAbsolutePath().normalize().toString())
				+ "\",\"cfg_sha256_after\":\"" + cfgSha
				+ "\",\"cfg_unchanged\":" + unchanged
				+ ",\"outcome\":\"COMPLETE_OFFLINE\","
				+ "\"origin\":\"JAAMSIM_GUI_RCL\","
				+ "\"report_sha256\":\"" + reportSha + "\"}";
	}

	private static void expectHistoricalStatus(Method lookup, Path outputRoot, Path cfg,
			boolean expected, String context) throws Exception {
		Path found = (Path) lookup.invoke(null, outputRoot, cfg, sha256(cfg));
		if ((found != null) != expected)
			throw new AssertionError(context + ": expected reuse=" + expected + ", found=" + found);
		checks++;
	}

	private static void expectRoot(Class<?> window, File model, Path configuredRoot,
			Path expectedRoot, String reason) throws Exception {
		Method lookup = window.getDeclaredMethod("findAssistantRoot", File.class);
		lookup.setAccessible(true);
		String previous = System.getProperty("jaamsim.assistant.root");
		try {
			System.setProperty("jaamsim.assistant.root", configuredRoot.toString());
			Path found = (Path) lookup.invoke(null, model);
			if (expectedRoot == null ? found != null : !expectedRoot.equals(found)) {
				throw new AssertionError(window.getSimpleName() + " / " + reason
						+ ": expected=" + expectedRoot + ", actual=" + found);
			}
			checks++;
		}
		finally {
			if (previous == null)
				System.clearProperty("jaamsim.assistant.root");
			else
				System.setProperty("jaamsim.assistant.root", previous);
		}
	}

	private static void expectLauncherPrecedence(
			String environmentValue, String propertyValue, String expected, String context) {
		String selected = AssistantLaunchSettings.preferLauncherEnvironment(
				environmentValue, propertyValue);
		if (expected == null ? selected != null : !expected.equals(selected))
			throw new AssertionError("Launcher precedence " + context
					+ ": expected=" + expected + ", found=" + selected);
		checks++;
	}

	public static void main(String[] args) throws Exception {
		Path temp = Files.createTempDirectory("jaam-rcl-contract-");
		Path repositoryRoot = temp.resolve("JAAM_AI_NATIVE");
		Path assistantRoot = repositoryRoot.resolve("extensions").resolve("academic-assistant");
		Path cfg = assistantRoot.resolve("examples").resolve("jaamsim").resolve("demo.cfg");
		Path otherCfg = assistantRoot.resolve("examples").resolve("jaamsim").resolve("unrelated.cfg");
		Path run = assistantRoot.resolve("output").resolve("offline-review").resolve("test_run");
		Files.createDirectories(cfg.getParent());
		Files.createDirectories(run);
		Files.write(cfg, "RecordEdits\n".getBytes(StandardCharsets.UTF_8));
		Files.write(otherCfg, "OtherConfig\n".getBytes(StandardCharsets.UTF_8));
		Path report = run.resolve("demo_offline_review.json");
		Path status = run.resolve("demo_suggestions_status.json");

		Method verifier = AIAssistantBox.class.getDeclaredMethod("validateOfflineRclReport",
				Path.class, Path.class, String.class, Path.class);
		verifier.setAccessible(true);

		Files.writeString(status, statuses(cfg, "demo"));
		Files.writeString(report, report(cfg, "demo", false, false));
		expectValid(verifier, report, cfg, assistantRoot);

		// Python display_path() makes paths relative to academic-assistant,
		// not the enclosing JAAM_AI_NATIVE directory.
		Path relative = assistantRoot.relativize(cfg);
		String absolute = escape(cfg.toAbsolutePath().normalize().toString());
		Files.writeString(report, report(cfg, "demo", false, false)
				.replace(absolute, escape(relative.toString())));
		Files.writeString(status, statuses(cfg, "demo")
				.replace(absolute, escape(relative.toString())));
		expectValid(verifier, report, cfg, assistantRoot);

		// The same relative string interpreted against JAAM_AI_NATIVE is wrong.
		// It must not be accepted as provenance for this model.
		Path staleNativeRelative = repositoryRoot.relativize(cfg);
		Files.writeString(report, report(cfg, "demo", false, false)
				.replace(absolute, escape(staleNativeRelative.toString())));
		Files.writeString(status, statuses(cfg, "demo"));
		expectBlocked(verifier, report, cfg, assistantRoot);

		Files.writeString(report, "{not valid JSON}");
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(report, report(otherCfg, "demo", false, false));
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(report, report(cfg, "another_model", false, false));
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(report, report(cfg, "demo", true, false));
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(report, report(cfg, "demo", false, true));
		expectBlocked(verifier, report, cfg, assistantRoot);

		Files.writeString(report, report(cfg, "demo", false, false));
		Files.delete(status);
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(status, statuses(otherCfg, "demo"));
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(status, statuses(cfg, "different"));
		expectBlocked(verifier, report, cfg, assistantRoot);
		Files.writeString(status, "{not valid JSON}");
		expectBlocked(verifier, report, cfg, assistantRoot);

		// Decision import is a separate risk: verify the entire receipt + status
		// chain for the same CFG before carrying an old operator decision forward.
		Method lookup = AIAssistantBox.class.getDeclaredMethod("findSuggestionStatusFile",
				Path.class, Path.class, String.class);
		lookup.setAccessible(true);
		Path historyRoot = run.getParent();
		Path receiptFile = run.resolve("JAAM_AI_OFFLINE_REVIEW_RECEIPT.json");
		Files.writeString(report, report(cfg, "demo", false, false)
				.replace(absolute, escape(relative.toString())));
		Files.writeString(status, statuses(cfg, "demo")
				.replace(absolute, escape(relative.toString())));
		Files.writeString(receiptFile, receipt(cfg, sha256(cfg), sha256(report), true));
		expectHistoricalStatus(lookup, historyRoot, cfg, true, "same model + hash + relative source");

		Files.writeString(receiptFile, receipt(cfg, "old-hash", sha256(report), true));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "changed model hash");

		Files.writeString(receiptFile, receipt(cfg, sha256(cfg), sha256(report), false));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "CFG changed during review");

		Files.writeString(receiptFile, receipt(cfg, sha256(cfg), sha256(report), true));
		Files.writeString(report, report(otherCfg, "demo", false, false));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "report belongs to another source");

		Files.writeString(report, report(cfg, "demo", false, false)
				.replace(absolute, escape(relative.toString())));
		// Hash from the original version of the report is no longer valid.
		Files.writeString(receiptFile, receipt(cfg, sha256(cfg), "tampered-report", true));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "report hash pin mismatch");

		Files.writeString(receiptFile, receipt(cfg, sha256(cfg), sha256(report), true));
		Files.writeString(status, statuses(otherCfg, "demo"));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "status belongs to another model");

		Files.writeString(status, statuses(cfg, "demo")
				.replace(absolute, escape(relative.toString())));
		Files.delete(receiptFile);
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "unattested history");
		// CMD reviews let the Python parser choose its normalized model ID;
		// Java must import this same-CFG review without requiring its own GUI ID.
		Path cmdRun = historyRoot.resolve("cmd_run");
		Files.createDirectories(cmdRun);
		Path cmdReport = cmdRun.resolve("demo_cli_id_offline_review.json");
		Path cmdStatus = cmdRun.resolve("demo_cli_id_suggestions_status.json");
		Path cmdReceipt = cmdRun.resolve("JAAM_AI_OFFLINE_REVIEW_RECEIPT.json");
		Files.writeString(cmdReport, report(cfg, "demo_cli_id", false, false)
				.replace(absolute, escape(relative.toString())));
		Files.writeString(cmdStatus, statuses(cfg, "demo_cli_id")
				.replace(absolute, escape(relative.toString())));
		Files.writeString(cmdReceipt, receipt(cfg, sha256(cfg), sha256(cmdReport), true)
				.replace("JAAMSIM_GUI_RCL", "CMD_CENTRAL"));
		expectHistoricalStatus(lookup, historyRoot, cfg, true, "CMD parser model ID differs from Java GUI ID");

		// More than one report per run must never lead to an arbitrary pick.
		Path extraReport = cmdRun.resolve("other_offline_review.json");
		Files.writeString(extraReport, report(cfg, "other", false, false));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "ambiguous multiple reports");
		Files.delete(extraReport);
		expectHistoricalStatus(lookup, historyRoot, cfg, true, "single report restored");

		// A report can declare an unsafe ID; it must not be usable as a path.
		Files.writeString(cmdReport, report(cfg, "..", false, false));
		Files.writeString(cmdReceipt, receipt(cfg, sha256(cfg), sha256(cmdReport), true)
				.replace("JAAMSIM_GUI_RCL", "CMD_CENTRAL"));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "unsafe report model ID");

		Files.writeString(cmdReport, report(cfg, "demo_cli_id", false, false)
				.replace(absolute, escape(relative.toString())));
		Files.writeString(cmdReceipt, receipt(cfg, sha256(cfg), sha256(cmdReport), true)
				.replace("JAAMSIM_GUI_RCL", "CMD_CENTRAL"));
		Files.writeString(cmdStatus, statuses(cfg, "wrong_model"));
		expectHistoricalStatus(lookup, historyRoot, cfg, false, "CMD status model ID mismatch");

		Files.writeString(cmdStatus, statuses(cfg, "demo_cli_id")
				.replace(absolute, escape(relative.toString())));
		expectHistoricalStatus(lookup, historyRoot, cfg, true, "CMD status restored");
		// Both native windows must treat an explicit root as authoritative.
		// The CFG is deliberately next to an alternate valid module: silent
		// fallback would find it and incorrectly accept the invalid setting.
		Path python = assistantRoot.resolve("python");
		Files.createDirectories(python);
		Files.writeString(python.resolve("modulo_ia_offline.py"), "# placeholder");
		Files.writeString(python.resolve("statfit_auxiliar.py"), "# placeholder");
		Path missing = temp.resolve("missing-extension-root");
		expectRoot(AIAssistantBox.class, cfg.toFile(), missing, null,
				"invalid explicit root must not fall back to CFG directory");
		expectRoot(StatFitAssistantBox.class, cfg.toFile(), missing, null,
				"invalid explicit root must not fall back to CFG directory");
		expectRoot(AIAssistantBox.class, cfg.toFile(), assistantRoot, assistantRoot,
				"configured direct extension root");
		expectRoot(StatFitAssistantBox.class, cfg.toFile(), assistantRoot, assistantRoot,
				"configured direct extension root");
		expectRoot(AIAssistantBox.class, cfg.toFile(), repositoryRoot, assistantRoot,
				"configured native root with nested extension");
		expectRoot(StatFitAssistantBox.class, cfg.toFile(), repositoryRoot, assistantRoot,
				"configured native root with nested extension");
		// A directory with only the other window's script is not sufficient.
		Path wrongScript = temp.resolve("wrong-script-extension");
		Files.createDirectories(wrongScript.resolve("python"));
		Files.writeString(wrongScript.resolve("python").resolve("statfit_auxiliar.py"), "# placeholder");
		expectRoot(AIAssistantBox.class, cfg.toFile(), wrongScript, null,
				"explicit root missing AI script");
		Files.delete(wrongScript.resolve("python").resolve("statfit_auxiliar.py"));
		Files.writeString(wrongScript.resolve("python").resolve("modulo_ia_offline.py"), "# placeholder");
		expectRoot(StatFitAssistantBox.class, cfg.toFile(), wrongScript, null,
				"explicit root missing StatFit script");

		// These are the environment/property pairs visible to *both*
		// AIAssistantBox and StatFitAssistantBox via the shared helper.
		// The CMD environment is authoritative even when a Java -D value
		// exists or points to a different unverified extension/interpreter.
		expectLauncherPrecedence("  C:\\verified\\assistant  ",
				"C:\\unverified\\assistant", "C:\\verified\\assistant",
				"pinned extension root supersedes -D");
		expectLauncherPrecedence("  C:\\missing\\assistant  ",
				assistantRoot.toString(), "C:\\missing\\assistant",
				"invalid explicit environment does not fall back to -D");
		expectLauncherPrecedence(" C:\\verified\\python.exe ",
				"C:\\wrong\\python.exe", "C:\\verified\\python.exe",
				"pinned Python supersedes -D");
		expectLauncherPrecedence(" C:\\missing\\python.exe ",
				"python", "C:\\missing\\python.exe",
				"invalid explicit Python cannot silently revert to -D");
		expectLauncherPrecedence(null, "  /independent/assistant  ",
				"/independent/assistant", "standalone Java property fallback");
		expectLauncherPrecedence("", "  /standalone/python  ",
				"/standalone/python", "empty environment uses -D Python");
		expectLauncherPrecedence("   ", " /standalone/root ",
				"/standalone/root", "whitespace environment uses -D root");
		expectLauncherPrecedence(null, null, null, "no root explicitly configured");
		expectLauncherPrecedence(null, "  ", null, "blank Java property");
		expectLauncherPrecedence(" python.exe ", null, "python.exe",
				"environment command name remains intact");
		// New RCL reports provide locally verifiable interpreter evidence.
		// The executable here is a fixture file; no Python is launched by this test.
		Path fixtureExe = temp.resolve("fixture-python.exe");
		Files.writeString(fixtureExe, "fixture-binary-contents");
		Path fixtureScript = python.resolve("modulo_ia_offline.py");
		String runtime = runtime(fixtureExe, fixtureScript);
		Files.writeString(report, addRuntime(report(cfg, "demo", false, false), runtime));
		Files.writeString(status, addRuntime(statuses(cfg, "demo"), runtime));
		expectValid(verifier, report, cfg, assistantRoot);

		String wrongExeDigest = runtime.replace(sha256(fixtureExe), "0".repeat(64));
		Files.writeString(report, addRuntime(report(cfg, "demo", false, false), wrongExeDigest));
		Files.writeString(status, addRuntime(statuses(cfg, "demo"), wrongExeDigest));
		expectBlocked(verifier, report, cfg, assistantRoot);

		String wrongScriptDigest = runtime.replace(sha256(fixtureScript), "1".repeat(64));
		Files.writeString(report, addRuntime(report(cfg, "demo", false, false), wrongScriptDigest));
		Files.writeString(status, addRuntime(statuses(cfg, "demo"), wrongScriptDigest));
		expectBlocked(verifier, report, cfg, assistantRoot);

		String badVersion = runtime.replace("3.11.9", "3.10.13");
		Files.writeString(report, addRuntime(report(cfg, "demo", false, false), badVersion));
		Files.writeString(status, addRuntime(statuses(cfg, "demo"), badVersion));
		expectBlocked(verifier, report, cfg, assistantRoot);

		Files.writeString(report, addRuntime(report(cfg, "demo", false, false), runtime));
		Files.writeString(status, statuses(cfg, "demo"));
		expectBlocked(verifier, report, cfg, assistantRoot);

		Files.writeString(status, addRuntime(statuses(cfg, "demo"), runtime));
		String wrongScriptRuntime = runtime.replace(
				escape(fixtureScript.toRealPath().toString()),
				escape(python.resolve("another_script.py").toString()));
		Files.writeString(report, addRuntime(report(cfg, "demo", false, false), wrongScriptRuntime));
		expectBlocked(verifier, report, cfg, assistantRoot);

		System.out.println("RCL_REPORT_PROVENANCE_CONTRACT_OK " + checks);
	}
}
