/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * Headless synthetic output contracts; does not launch Python/JaamSim.
 */
package com.jaamsim.ui;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

public final class StatFitRunArtifactsContractTest {
	private static int checks = 0;

	private static String escape(Path path) {
		return path.toAbsolutePath().normalize().toString()
				.replace("\\", "\\\\").replace("\"", "\\\"");
	}

	private static void expect(boolean valid, String reason) {
		if (!valid)
			throw new AssertionError(reason);
		checks++;
	}

	private static void expectBlocked(String reason, Checked action) throws Exception {
		try {
			action.run();
			throw new AssertionError("Expected fail-closed: " + reason);
		}
		catch (java.io.IOException expected) {
			checks++;
		}
	}

	private interface Checked {
		void run() throws Exception;
	}

	private static String runtime() {
		return "{\"schema\":\"jaam.ai.python_runtime.v1\"}";
	}

	private static Path put(Path folder, String name, String contents) throws Exception {
		Path file = folder.resolve(name);
		Files.write(file, contents.getBytes(StandardCharsets.UTF_8));
		return file;
	}

	private static String prepareOutput(Map<String, Path> files) {
		return "Coluna preparada: tempo\nCSV limpo: " + files.get("csv")
				+ "\nRelatório Markdown: " + files.get("markdown")
				+ "\nRelatório JSON: " + files.get("json") + "\n";
	}

	private static String fitOutput(Map<String, Path> files) {
		return "Melhor distribuição: normal\n"
				+ "Relatório Markdown: " + files.get("markdown")
				+ "\nRelatório JSON: " + files.get("json")
				+ "\nGráfico histograma: " + files.get("histogram")
				+ "\nGráfico CDF empírica: " + files.get("ecdf")
				+ "\nGráfico Q-Q: " + files.get("qq")
				+ "\nGráfico P-P: " + files.get("pp")
				+ "\nSnippet JaamSim: " + files.get("snippet") + "\n";
	}

	private static Map<String, Path> putPrepared(Path run) throws Exception {
		Map<String, Path> files = new HashMap<>();
		files.put("csv", put(run, "tempo_dados_preparados.csv", "tempo\n1\n2\n"));
		files.put("markdown", put(run, "tempo_data_assist.md", "# preparado"));
		String json = "{\"online_assist_enabled\":false,\"online_assist_used\":false,"
				+ "\"python_runtime\":" + runtime() + ","
				+ "\"cleaned_csv_path\":\"" + escape(files.get("csv")) + "\"}";
		files.put("json", put(run, "tempo_data_assist.json", json));
		return files;
	}

	private static Map<String, Path> putFit(Path run) throws Exception {
		Map<String, Path> files = new HashMap<>();
		files.put("markdown", put(run, "tempo_statfit_report.md", "# ajuste"));
		files.put("histogram", put(run, "tempo_histograma.svg", "<svg/>"));
		files.put("ecdf", put(run, "tempo_cdf_empirica.svg", "<svg/>"));
		files.put("qq", put(run, "tempo_qq_plot.svg", "<svg/>"));
		files.put("pp", put(run, "tempo_pp_plot.svg", "<svg/>"));
		files.put("snippet", put(run, "tempo_jaamsim_distribution.cfg", "# sugestão"));
		String json = "{\"best_distribution\":\"normal\",\"python_runtime\":" + runtime()
				+ ",\"chart_files\":{"
				+ "\"histogram_svg\":\"" + escape(files.get("histogram")) + "\","
				+ "\"ecdf_svg\":\"" + escape(files.get("ecdf")) + "\","
				+ "\"qq_svg\":\"" + escape(files.get("qq")) + "\","
				+ "\"pp_svg\":\"" + escape(files.get("pp")) + "\"}}";
		files.put("json", put(run, "tempo_statfit_report.json", json));
		return files;
	}

	public static void main(String[] args) throws Exception {
		Path root = Files.createTempDirectory("jaam-statfit-sessions-");
		Path firstPrepare = StatFitRunArtifacts.createRunDirectory(root, "prepare");
		Path secondPrepare = StatFitRunArtifacts.createRunDirectory(root, "prepare");
		Path fit = StatFitRunArtifacts.createRunDirectory(root, "fit");
		expect(!firstPrepare.equals(secondPrepare), "preparation sessions must be unique");
		expect(!secondPrepare.equals(fit), "fit and preparation must not share directories");
		expect(Files.isDirectory(firstPrepare) && Files.isDirectory(fit), "session roots exist");

		Map<String, Path> prepare = putPrepared(firstPrepare);
		StatFitRunArtifacts.Prepared verified = StatFitRunArtifacts.validatePreparation(
				firstPrepare, prepareOutput(prepare));
		expect(verified.csv.toPath().equals(prepare.get("csv")), "valid preparation bound to first run");
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_data_assist.json") == null,
				"unaccepted preparation not listed");
		StatFitRunArtifacts.recordAcceptedRun(firstPrepare, verified);
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_data_assist.json") != null,
				"accepted preparation appears in history");
		expectBlocked("cannot reuse another run's data file",
				() -> StatFitRunArtifacts.validatePreparation(secondPrepare, prepareOutput(prepare)));
		expectBlocked("require real prepared JSON",
				() -> StatFitRunArtifacts.validatePreparation(firstPrepare,
						prepareOutput(prepare).replace("_data_assist.json", "_data_assist_invalid.json")));
		Map<String, Path> anotherPrepare = putPrepared(secondPrepare);
		StatFitRunArtifacts.Prepared otherVerified =
				StatFitRunArtifacts.validatePreparation(secondPrepare, prepareOutput(anotherPrepare));
		expect(otherVerified.csv.toPath().equals(anotherPrepare.get("csv")),
				"same-named CSV in another run is independent");
		StatFitRunArtifacts.recordAcceptedRun(secondPrepare, otherVerified);

		String originalPreparation = Files.readString(prepare.get("json"));
		Files.writeString(prepare.get("json"), originalPreparation.replace(
				"\"online_assist_used\":false", "\"online_assist_used\":true"));
		expectBlocked("online preparation cannot be adopted",
				() -> StatFitRunArtifacts.validatePreparation(firstPrepare, prepareOutput(prepare)));
		Files.writeString(prepare.get("json"), originalPreparation);
		Files.writeString(prepare.get("json"), originalPreparation.replace(
				"\"python_runtime\":", "\"invalid_runtime\":"));
		expectBlocked("missing runtime is not accepted",
				() -> StatFitRunArtifacts.validatePreparation(firstPrepare, prepareOutput(prepare)));
		Files.writeString(prepare.get("json"), originalPreparation);

		Map<String, Path> fitted = putFit(fit);
		StatFitRunArtifacts.Fit validFit = StatFitRunArtifacts.validateFit(fit, fitOutput(fitted));
		expect(validFit.json.toPath().equals(fitted.get("json")), "fit JSON belongs to fit session");
		expect(validFit.histogram.toPath().equals(fitted.get("histogram")), "fit histogram belongs to same session");
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_statfit_report.json") == null,
				"unaccepted or partial fit cannot be browsed as success");
		StatFitRunArtifacts.recordAcceptedRun(fit, validFit);
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_statfit_report.json")
				.equals(fitted.get("json").toFile()), "accepted fit history is visible");

		String originalFit = Files.readString(fitted.get("json"));
		Files.writeString(fitted.get("json"), originalFit.replace(
				escape(fitted.get("histogram")), escape(firstPrepare.resolve("tempo_histograma.svg"))));
		expectBlocked("chart JSON cannot point to an old run",
				() -> StatFitRunArtifacts.validateFit(fit, fitOutput(fitted)));
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_statfit_report.json") == null,
				"altered report is hidden from accepted history");
		Files.writeString(fitted.get("json"), originalFit);

		expectBlocked("fit stdout cannot import old report",
				() -> StatFitRunArtifacts.validateFit(fit, fitOutput(fitted).replace(
						fitted.get("json").toString(), anotherPrepare.get("json").toString())));
		Files.delete(fitted.get("snippet"));
		expectBlocked("missing snippet must not be treated as complete",
				() -> StatFitRunArtifacts.validateFit(fit, fitOutput(fitted)));
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_jaamsim_distribution.cfg") == null,
				"deleted snippet no longer appears in history");

		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_statfit_report.json")
				.equals(fitted.get("json").toFile()), "latest run report remains visible in history");
		expect(StatFitRunArtifacts.findLatestFile(root.toFile(), "_data_assist.json") != null,
				"historical data preparations remain visible");
		expectBlocked("malformed command path rejected",
				() -> StatFitRunArtifacts.requireCurrentRunFile(fit,
						"Relatório JSON: ../tempo_statfit_report.json", "_statfit_report.json", "Relatório JSON:"));
		System.out.println("STATFIT_RUN_ARTIFACT_CONTRACT_OK " + checks);
	}
}
