/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * Headless contract regression for JaamSim's offline RCL report provenance.
 * No JFrame, simulation engine, Python interpreter, network or CFG execution.
 */
package com.jaamsim.ui;

import java.lang.reflect.Method;
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

		System.out.println("RCL_REPORT_PROVENANCE_CONTRACT_OK " + checks);
	}
}
