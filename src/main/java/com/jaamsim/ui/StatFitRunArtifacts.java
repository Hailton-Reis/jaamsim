/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * Static, headless output-contract checks. No Python, JaamSim simulation,
 * GUI, model inference or network calls are executed here.
 */
package com.jaamsim.ui;

import java.io.File;
import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.nio.file.StandardCopyOption;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.UUID;
import java.util.stream.Stream;

import com.jaamsim.JSON.JSONParser;
import com.jaamsim.JSON.JSONValue;
import com.jaamsim.JSON.JSONWriter;

final class StatFitRunArtifacts {
	private StatFitRunArtifacts() {}

	static final class Prepared {
		final File csv;
		final File markdown;
		final File json;

		Prepared(Path csv, Path markdown, Path json) {
			this.csv = csv.toFile();
			this.markdown = markdown.toFile();
			this.json = json.toFile();
		}
	}

	static final class Fit {
		final File markdown;
		final File json;
		final File histogram;
		final File ecdf;
		final File qq;
		final File pp;
		final File snippet;

		Fit(Path markdown, Path json, Path histogram, Path ecdf,
				Path qq, Path pp, Path snippet) {
			this.markdown = markdown.toFile();
			this.json = json.toFile();
			this.histogram = histogram.toFile();
			this.ecdf = ecdf.toFile();
			this.qq = qq.toFile();
			this.pp = pp.toFile();
			this.snippet = snippet.toFile();
		}
	}

	static Path createRunDirectory(Path statfitRoot, String kind) throws IOException {
		if (!"fit".equals(kind) && !"prepare".equals(kind))
			throw new IllegalArgumentException("Unknown StatFit run category");
		Path history = statfitRoot.resolve("runs");
		Files.createDirectories(history);
		String utc = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss_SSS")
				.withZone(ZoneOffset.UTC).format(Instant.now());
		return Files.createDirectory(history.resolve(kind + "_" + utc + "_"
				+ UUID.randomUUID().toString().replace("-", "").substring(0, 12)));
	}

	private static String outputValue(String stdout, String... labels) {
		if (stdout == null)
			return null;
		for (String line : stdout.split("\\R")) {
			String trimmed = line.trim();
			for (String label : labels) {
				if (trimmed.startsWith(label))
					return trimmed.substring(label.length()).trim();
			}
		}
		return null;
	}

	static Path requireCurrentRunFile(Path run, String stdout, String suffix, String... labels)
			throws IOException {
		String value = outputValue(stdout, labels);
		if (value == null || value.isEmpty())
			throw new IOException("Saída não informa arquivo: " + suffix);
		return requireFile(run, value, suffix);
	}

	private static Path requireFile(Path run, String raw, String suffix) throws IOException {
		Path directory = run.toRealPath();
		Path candidate = Paths.get(raw);
		if (!candidate.isAbsolute())
			throw new IOException("Resultado sem caminho absoluto: " + suffix);
		candidate = candidate.toAbsolutePath().normalize();
		if (!candidate.getParent().toRealPath().equals(directory)
				|| !candidate.getFileName().toString().endsWith(suffix)
				|| !Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS))
			throw new IOException("Arquivo não pertence à execução atual: " + suffix);
		return candidate;
	}

	private static JSONValue readObject(Path json) throws IOException {
		try {
			JSONValue root = JSONParser.parse(new String(
					Files.readAllBytes(json), StandardCharsets.UTF_8));
			if (root == null || !root.isMap())
				throw new IOException("Relatório JSON inválido");
			return root;
		}
		catch (IOException ex) {
			throw ex;
		}
		catch (Exception ex) {
			throw new IOException("Não foi possível validar o relatório JSON", ex);
		}
	}

	private static JSONValue member(JSONValue root, String key) {
		return root != null && root.isMap() ? root.mapVal.get(key) : null;
	}

	private static String text(JSONValue root, String key) {
		JSONValue value = member(root, key);
		return value != null && value.isString() ? value.stringVal : "";
	}

	private static void requireRuntime(JSONValue root) throws IOException {
		if (!"jaam.ai.python_runtime.v1".equals(text(member(root, "python_runtime"), "schema")))
			throw new IOException("Relatório sem proveniência Python da execução");
	}

	static Prepared validatePreparation(Path run, String stdout) throws IOException {
		Path csv = requireCurrentRunFile(run, stdout, "_dados_preparados.csv", "CSV limpo:");
		Path markdown = requireCurrentRunFile(run, stdout, "_data_assist.md", "Relatório Markdown:", "Relatorio Markdown:");
		Path json = requireCurrentRunFile(run, stdout, "_data_assist.json", "Relatório JSON:", "Relatorio JSON:");
		JSONValue report = readObject(json);
		requireRuntime(report);
		JSONValue enabled = member(report, "online_assist_enabled");
		JSONValue used = member(report, "online_assist_used");
		if (enabled == null || !enabled.isFalse() || used == null || !used.isFalse())
			throw new IOException("Preparação não confirmou modo offline");
		if (!csv.equals(requireFile(run, text(report, "cleaned_csv_path"), "_dados_preparados.csv")))
			throw new IOException("CSV do relatório não coincide com a execução");
		return new Prepared(csv, markdown, json);
	}

	static Fit validateFit(Path run, String stdout) throws IOException {
		Path markdown = requireCurrentRunFile(run, stdout, "_statfit_report.md", "Relatório Markdown:", "Relatorio Markdown:");
		Path json = requireCurrentRunFile(run, stdout, "_statfit_report.json", "Relatório JSON:", "Relatorio JSON:");
		Path histogram = requireCurrentRunFile(run, stdout, "_histograma.svg", "Gráfico histograma:", "Grafico histograma:");
		Path ecdf = requireCurrentRunFile(run, stdout, "_cdf_empirica.svg", "Gráfico CDF empírica:", "Grafico CDF empirica:");
		Path qq = requireCurrentRunFile(run, stdout, "_qq_plot.svg", "Gráfico Q-Q:", "Grafico Q-Q:");
		Path pp = requireCurrentRunFile(run, stdout, "_pp_plot.svg", "Gráfico P-P:", "Grafico P-P:");
		Path snippet = requireCurrentRunFile(run, stdout, "_jaamsim_distribution.cfg", "Snippet JaamSim:");
		JSONValue report = readObject(json);
		requireRuntime(report);
		JSONValue charts = member(report, "chart_files");
		if (charts == null || !charts.isMap()
				|| !histogram.equals(requireFile(run, text(charts, "histogram_svg"), "_histograma.svg"))
				|| !ecdf.equals(requireFile(run, text(charts, "ecdf_svg"), "_cdf_empirica.svg"))
				|| !qq.equals(requireFile(run, text(charts, "qq_svg"), "_qq_plot.svg"))
				|| !pp.equals(requireFile(run, text(charts, "pp_svg"), "_pp_plot.svg")))
			throw new IOException("Gráficos do relatório não correspondem à execução");
		if (text(report, "best_distribution").isEmpty())
			throw new IOException("Relatório não informa distribuição candidata");
		return new Fit(markdown, json, histogram, ecdf, qq, pp, snippet);
	}

	/**
	 * Only a fully validated run receives this local receipt. Every artifact
	 * hash is recorded so later browsing cannot accidentally select partial
	 * outputs from a failed run. This is local integrity, not a signature.
	 */
	static void recordAcceptedRun(Path run, Prepared accepted) throws IOException {
		writeReceipt(run, "prepare", accepted.csv, accepted.markdown, accepted.json);
	}

	static void recordAcceptedRun(Path run, Fit accepted) throws IOException {
		writeReceipt(run, "fit", accepted.markdown, accepted.json, accepted.histogram,
				accepted.ecdf, accepted.qq, accepted.pp, accepted.snippet);
	}

	private static void writeReceipt(Path run, String kind, File... files) throws IOException {
		Path directory = run.toRealPath();
		JSONValue receipt = JSONValue.makeObject();
		receipt.mapVal.put("schema", JSONValue.makeStringVal("jaam.statfit.run_receipt.v1"));
		receipt.mapVal.put("run_id", JSONValue.makeStringVal(directory.getFileName().toString()));
		receipt.mapVal.put("kind", JSONValue.makeStringVal(kind));
		receipt.mapVal.put("outcome", JSONValue.makeStringVal("COMPLETE_LOCAL"));
		JSONValue artifacts = JSONValue.makeObject();
		for (File file : files) {
			Path candidate = file.toPath();
			if (!Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)
					|| !candidate.getParent().toRealPath().equals(directory))
				throw new IOException("Não foi possível registrar arquivo de outra execução");
			artifacts.mapVal.put(candidate.getFileName().toString(),
					JSONValue.makeStringVal(sha256File(candidate)));
		}
		receipt.mapVal.put("artifact_sha256", artifacts);
		Path temporary = directory.resolve("STATFIT_RUN_RECEIPT.tmp");
		Path target = directory.resolve("STATFIT_RUN_RECEIPT.json");
		Files.write(temporary, (JSONWriter.writeJSONValue(receipt) + "\n")
				.getBytes(StandardCharsets.UTF_8));
		Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
	}

	private static String sha256File(Path file) throws IOException {
		try {
			MessageDigest md = MessageDigest.getInstance("SHA-256");
			try (java.io.InputStream input = Files.newInputStream(file)) {
				byte[] buf = new byte[16384];
				int length;
				while ((length = input.read(buf)) != -1)
					md.update(buf, 0, length);
			}
			StringBuilder digest = new StringBuilder();
			for (byte b : md.digest())
				digest.append(String.format(java.util.Locale.ROOT, "%02x", b & 0xff));
			return digest.toString();
		}
		catch (NoSuchAlgorithmException ex) {
			throw new IOException("SHA-256 unavailable", ex);
		}
	}

	private static boolean isAcceptedRunArtifact(Path run, Path candidate) {
		Path receiptFile = run.resolve("STATFIT_RUN_RECEIPT.json");
		if (!Files.isRegularFile(receiptFile, LinkOption.NOFOLLOW_LINKS))
			return false;
		try {
			JSONValue receipt = readObject(receiptFile);
			if (!"jaam.statfit.run_receipt.v1".equals(text(receipt, "schema"))
					|| !"COMPLETE_LOCAL".equals(text(receipt, "outcome"))
					|| !run.getFileName().toString().equals(text(receipt, "run_id")))
				return false;
			JSONValue artifacts = member(receipt, "artifact_sha256");
			String recorded = text(artifacts, candidate.getFileName().toString());
			return !recorded.isEmpty() && recorded.equalsIgnoreCase(sha256File(candidate));
		}
		catch (Exception ex) {
			return false;
		}
	}

	/**
	 * Show the latest successful-looking local artifact in direct legacy
	 * folders or one level below runs/. Never recurse arbitrarily or follow
	 * symlinked run directories. This is browsing, not success attestation.
	 */
	static File findLatestFile(File root, String suffix) {
		Path base = root.toPath();
		if (!Files.isDirectory(base, LinkOption.NOFOLLOW_LINKS))
			return null;
		Path newest = null;
		try {
			try (Stream<Path> oldFiles = Files.list(base)) {
				for (Path file : (Iterable<Path>) oldFiles::iterator)
					if (matches(file, suffix) && newer(file, newest))
						newest = file;
			}
			Path history = base.resolve("runs");
			if (Files.isDirectory(history, LinkOption.NOFOLLOW_LINKS)) {
				try (Stream<Path> runs = Files.list(history)) {
					for (Path run : (Iterable<Path>) runs::iterator) {
						if (!Files.isDirectory(run, LinkOption.NOFOLLOW_LINKS))
							continue;
						try (Stream<Path> files = Files.list(run)) {
							for (Path file : (Iterable<Path>) files::iterator)
								if (matches(file, suffix) && newer(file, newest)
										&& isAcceptedRunArtifact(run, file))
									newest = file;
						}
						catch (IOException ex) {
							// Ignore an unreadable historical run.
						}
					}
				}
			}
		}
		catch (IOException ex) {
			return newest == null ? null : newest.toFile();
		}
		return newest == null ? null : newest.toFile();
	}

	private static boolean matches(Path path, String suffix) {
		return Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
				&& path.getFileName().toString().endsWith(suffix);
	}

	private static boolean newer(Path path, Path old) {
		if (old == null)
			return true;
		try {
			return Files.getLastModifiedTime(path).compareTo(Files.getLastModifiedTime(old)) > 0;
		}
		catch (IOException ex) {
			return false;
		}
	}
}
