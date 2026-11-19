/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 *
 * End-to-end C2 preflight with actual JaamSim JSON parser and Python subprocess.
 * Uses only synthetic documents. Does NOT run a model, GUI, external LLM,
 * state tool or confirmatory experiment.
 */
package com.jaamsim.ui;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public final class C2PythonInteropContractTest {
    private static int checks;

    private static void expect(boolean condition, String message) {
        if (!condition)
            throw new AssertionError(message);
        checks++;
    }

    private static void blocked(Path root, Path corpus, Path manifest, String python) throws Exception {
        try {
            C2PreflightRunner.execute(root, corpus, manifest, "Queue Server", python);
            throw new AssertionError("fail-open: invalid corpus manifest");
        }
        catch (IOException expected) {
            checks++;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1)
            throw new IllegalArgumentException("Usage: [python command]");
        String python = args.length == 1 ? args[0] : "python3";
        Path root = Path.of("extensions", "academic-assistant").toAbsolutePath().normalize();
        Path examples = root.resolve("examples").resolve("c2-preflight");
        Path corpus = examples.resolve("corpus");
        Path manifest = examples.resolve("manifest.json");
        expect(Files.isRegularFile(root.resolve("python/c2_chat_bridge.py")), "bridge installed");
        expect(Files.isRegularFile(root.resolve("python/simulation_chat_assist.py")), "chat prompt source exists");
        C2PreflightRunner.Outcome positive = C2PreflightRunner.execute(
                root, corpus, manifest, "Queue Server", python);
        expect(!positive.noEvidence && !positive.hits.isEmpty(), "positive synthetic evidence");
        expect(positive.displayText().contains("GUIA_SYNTH:L"), "citation preserved through Java parser");
        expect(positive.displayText().contains("não é resposta de IA"), "never claims online inference");
        C2PreflightRunner.Outcome absent = C2PreflightRunner.execute(
                root, corpus, manifest, "xylophonuradazquert", python);
        expect(absent.noEvidence && absent.hits.isEmpty(), "unknown query must abstain");

        Path scratch = Files.createTempDirectory("jaam-c2-interop-");
        try {
            Path tempCorpus = Files.createDirectory(scratch.resolve("corpus"));
            try (Stream<Path> stream = Files.list(corpus)) {
                for (Path file : stream.toList())
                    Files.copy(file, tempCorpus.resolve(file.getFileName()));
            }
            Path badManifest = scratch.resolve("manifest.json");
            String original = Files.readString(manifest, StandardCharsets.UTF_8);
            Files.writeString(badManifest,
                    original.replaceFirst("(?i)[0-9a-f]{64}", "0".repeat(64)),
                    StandardCharsets.UTF_8);
            blocked(root, tempCorpus, badManifest, python);
        }
        finally {
            try (Stream<Path> stream = Files.walk(scratch)) {
                for (Path file : stream.sorted(Comparator.reverseOrder()).toList())
                    Files.deleteIfExists(file);
            }
        }
        System.out.println("C2 Java/Python real JSON interop PASS: " + checks + " checks");
    }
}
