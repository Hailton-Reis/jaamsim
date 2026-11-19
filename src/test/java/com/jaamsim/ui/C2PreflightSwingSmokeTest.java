/* Copyright 2026 Hailton Santos Reis; SPDX-License-Identifier: Apache-2.0 */
package com.jaamsim.ui;

import java.awt.GraphicsEnvironment;
import java.awt.Robot;
import java.awt.Rectangle;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.concurrent.atomic.AtomicReference;
import javax.imageio.ImageIO;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;

/** Synthetic C2 preflight only: no JaamSim model, LLM, RCL or CFG writes. */
public final class C2PreflightSwingSmokeTest {
    private static C2PreflightPanel panel;
    private static JFrame frame;
    private static int checks;
    private static final AtomicReference<Throwable> edtFailure = new AtomicReference<>();
    private static void ok(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
        checks++;
    }
    private static void edt(Runnable action) throws Exception {
        SwingUtilities.invokeAndWait(() -> {
            try { action.run(); }
            catch (Throwable failure) { edtFailure.set(failure); }
        });
        Throwable failure = edtFailure.getAndSet(null);
        if (failure != null) throw new AssertionError("Swing EDT failure", failure);
    }
    private static <T> T field(String name, Class<T> type) {
        try {
            Field f = C2PreflightPanel.class.getDeclaredField(name);
            f.setAccessible(true);
            return type.cast(f.get(panel));
        }
        catch (Exception failure) { throw new AssertionError(name, failure); }
    }
    private static String ask(String question, boolean shouldPass) throws Exception {
        JTextArea input = field("queryArea", JTextArea.class);
        JTextArea output = field("resultsArea", JTextArea.class);
        JLabel state = field("stateLabel", JLabel.class);
        JButton button = field("runButton", JButton.class);
        edt(() -> { input.setText(question); button.doClick(); ok(!button.isEnabled(), "busy button disabled"); });
        long end = System.nanoTime() + 30_000_000_000L;
        boolean[] done = {false};
        while (System.nanoTime() < end) {
            edt(() -> done[0] = button.isEnabled() && (state.getText().contains("concluída")
                    || state.getText().contains("Bloqueada")));
            if (done[0]) break;
            Thread.sleep(80);
        }
        String[] text = {""};
        edt(() -> {
            ok(done[0], "completed within timeout");
            ok(state.getText().contains(shouldPass ? "concluída" : "Bloqueada"), "correct status");
            text[0] = output.getText();
        });
        return text[0];
    }
    private static void capture(Path target) throws Exception {
        if (GraphicsEnvironment.isHeadless()) return;
        Rectangle[] bounds = new Rectangle[1];
        edt(() -> bounds[0] = frame.getBounds());
        ImageIO.write(new Robot().createScreenCapture(bounds[0]), "png", target.toFile());
        ok(Files.size(target) > 2_000, "PNG screenshot exists");
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("<assistant-root> <python> <evidence-dir>");
        Path root = Paths.get(args[0]).toAbsolutePath().normalize();
        Path evidence = Paths.get(args[2]).toAbsolutePath().normalize();
        Path corpus = root.resolve("examples/c2-preflight/corpus");
        Path manifest = root.resolve("examples/c2-preflight/manifest.json");
        ok(Files.isRegularFile(manifest), "manifest exists");
        Files.createDirectories(evidence);
        System.setProperty("jaamsim.assistant.root", root.toString());
        System.setProperty("jaamsim.python", args[1]);
        edt(() -> {
            panel = new C2PreflightPanel();
            if (!GraphicsEnvironment.isHeadless()) {
                frame = new JFrame("JAAM-AI C2 — synthetic GUI smoke");
                frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE);
                frame.setContentPane(panel);
                frame.setSize(1040, 830);
                frame.setLocation(30, 30);
                frame.setVisible(true);
            }
        });
        ok(panel != null, "Swing component created");
        JTextField corpusField = field("corpusField", JTextField.class);
        JTextField manifestField = field("manifestField", JTextField.class);
        edt(() -> {
            ok(corpusField.getText().equals(corpus.toString()), "launcher-based corpus");
            ok(manifestField.getText().equals(manifest.toString()), "launcher-based manifest");
        });
        String positive = ask("Queue Server", true);
        ok(positive.contains("GUIA_SYNTH:L"), "synthetic citation displayed");
        ok(positive.contains("DADOS NÃO CONFIÁVEIS"), "source labeled untrusted");
        ok(positive.contains("LLM=0, ferramentas de estado=0, escrita=0"), "non-execution visible");
        capture(evidence.resolve("c2_gui_citacoes.png"));
        edt(() -> {
            field("queryArea", JTextArea.class).setText("pergunta editada");
            ok(field("resultsArea", JTextArea.class).getText().isEmpty(), "edited input clears old result");
        });
        String missing = ask("xylophonuradazquert", true);
        ok(missing.contains("Nenhuma evidência encontrada"), "unknown terms abstain");
        ok(!missing.contains("[GUIA_SYNTH:L"), "abstention has no old citation");
        capture(evidence.resolve("c2_gui_abstencao.png"));
        Path disposable = Files.createTempDirectory("jaam-c2-swing-fixture-");
        try {
            Path alteredCorpus = Files.createDirectory(disposable.resolve("corpus"));
            try (java.util.stream.Stream<Path> files = Files.list(corpus)) {
                for (Path file : (Iterable<Path>) files::iterator)
                    Files.copy(file, alteredCorpus.resolve(file.getFileName()));
            }
            Path alteredManifest = Files.copy(manifest, disposable.resolve("manifest.json"));
            Files.writeString(alteredCorpus.resolve("guia_sintetico.txt"), "ALTERADO");
            edt(() -> { corpusField.setText(alteredCorpus.toString());
                        manifestField.setText(alteredManifest.toString()); });
            String blocked = ask("Queue Server", false);
            ok(blocked.contains("Pré-validação bloqueada"), "tampered corpus blocked");
            ok(!blocked.contains("[GUIA_SYNTH:L"), "blocked run does not reuse old results");
            capture(evidence.resolve("c2_gui_integridade_bloqueada.png"));
        }
        finally {
            try (java.util.stream.Stream<Path> walk = Files.walk(disposable)) {
                walk.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try { Files.deleteIfExists(path); } catch (Exception ignored) {}
                });
            }
        }
        edt(() -> { if (frame != null) frame.dispose(); });
        System.out.println("C2 Swing smoke PASS: " + checks + " checks; "
                + (GraphicsEnvironment.isHeadless() ? "headless" : "virtual desktop"));
        System.exit(0);
    }
}
