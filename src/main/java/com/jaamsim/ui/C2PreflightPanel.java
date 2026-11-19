/*
 * Copyright 2026 Hailton Santos Reis
 * SPDX-License-Identifier: Apache-2.0
 */
package com.jaamsim.ui;

import java.awt.BorderLayout;
import java.awt.FlowLayout;
import java.awt.GridBagConstraints;
import java.awt.GridBagLayout;
import java.awt.Insets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JFileChooser;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.SwingWorker;
import javax.swing.event.DocumentEvent;
import javax.swing.event.DocumentListener;

/** Deliberately separate from the normal chat and JaamSim model state. */
final class C2PreflightPanel extends JPanel {
    private final JTextField corpusField = new JTextField(42);
    private final JTextField manifestField = new JTextField(42);
    private final JTextArea queryArea = new JTextArea(3, 55);
    private final JTextArea resultsArea = new JTextArea(15, 55);
    private final JButton runButton = new JButton("Recuperar documentos (prévia)");
    private final JButton cancelButton = new JButton("Cancelar");
    // Mutated only on the Swing EDT. Equality of input strings alone misses ABA changes.
    private long inputRevision;
    private boolean cancellationRequested;
    private SwingWorker<C2PreflightRunner.Outcome, Void> activeWorker;
    private final JLabel stateLabel = new JLabel("Inativo — nenhuma consulta realizada");

    C2PreflightPanel() {
        super(new BorderLayout(8, 8));
        setBorder(BorderFactory.createEmptyBorder(10, 12, 10, 12));
        String rootSetting = AssistantLaunchSettings.preferLauncherEnvironment(
                System.getenv("JAAMSIM_ASSISTANT_ROOT"),
                System.getProperty("jaamsim.assistant.root"));
        if (rootSetting != null) {
            Path examples = Paths.get(rootSetting).toAbsolutePath().normalize()
                    .resolve("examples").resolve("c2-preflight");
            corpusField.setText(examples.resolve("corpus").toString());
            manifestField.setText(examples.resolve("manifest.json").toString());
        }
        JTextArea note = new JTextArea(
                "C2 — PRÉ-VALIDAÇÃO DOCUMENTAL (G0/G2 PENDENTES)\n"
                + "Consulta somente o corpus autorizado pelo manifesto SHA-256. "
                + "Não acessa o modelo JaamSim aberto, não chama IA nem altera .cfg.");
        note.setWrapStyleWord(true);
        note.setLineWrap(true);
        note.setRows(3);
        note.setEditable(false);
        note.setOpaque(false);
        JPanel topPanel = new JPanel(new BorderLayout(6, 6));
        topPanel.add(note, BorderLayout.NORTH);

        JPanel form = new JPanel(new GridBagLayout());
        GridBagConstraints g = new GridBagConstraints();
        g.gridx = 0; g.gridy = 0; g.weightx = 0; g.anchor = GridBagConstraints.WEST;
        g.insets = new Insets(4, 4, 4, 4);
        form.add(new JLabel("Pasta do corpus:"), g);
        g.gridx = 1; g.weightx = 1; g.fill = GridBagConstraints.HORIZONTAL;
        form.add(corpusField, g);
        JButton chooseCorpus = new JButton("Selecionar…");
        chooseCorpus.addActionListener(e -> choose(true));
        g.gridx = 2; g.weightx = 0; g.fill = GridBagConstraints.NONE;
        form.add(chooseCorpus, g);
        g.gridy = 1; g.gridx = 0;
        form.add(new JLabel("Manifesto:"), g);
        g.gridx = 1; g.weightx = 1; g.fill = GridBagConstraints.HORIZONTAL;
        form.add(manifestField, g);
        JButton chooseManifest = new JButton("Selecionar…");
        chooseManifest.addActionListener(e -> choose(false));
        g.gridx = 2; g.weightx = 0; g.fill = GridBagConstraints.NONE;
        form.add(chooseManifest, g);
        g.gridy = 2; g.gridx = 0; g.gridwidth = 3;
        form.add(new JLabel("Pergunta aos documentos (não é enviada ao chat comum):"), g);
        g.gridy = 3; g.weightx = 1; g.fill = GridBagConstraints.BOTH;
        queryArea.setLineWrap(true);
        queryArea.setWrapStyleWord(true);
        form.add(new JScrollPane(queryArea), g);
        JPanel controls = new JPanel(new FlowLayout(FlowLayout.LEFT));
        controls.add(runButton);
        cancelButton.setEnabled(false);
        controls.add(cancelButton);
        controls.add(stateLabel);
        g.gridy = 4; g.fill = GridBagConstraints.HORIZONTAL;
        form.add(controls, g);
        topPanel.add(form, BorderLayout.CENTER);
        add(topPanel, BorderLayout.NORTH);
        resultsArea.setEditable(false);
        resultsArea.setLineWrap(true);
        resultsArea.setWrapStyleWord(true);
        JScrollPane scroll = new JScrollPane(resultsArea);
        scroll.setBorder(BorderFactory.createTitledBorder("Fontes e citações — sem resposta de LLM"));
        add(scroll, BorderLayout.CENTER);
        runButton.addActionListener(e -> beginPreflight());
        cancelButton.addActionListener(e -> cancelPreflight());
        // A previously retrieved citation never remains visible for a new query/corpus.
        DocumentListener staleResults = new DocumentListener() {
            private void changed() {
                inputRevision++;
                resultsArea.setText("");
                stateLabel.setText("Entrada alterada — execute nova consulta");
            }
            @Override public void insertUpdate(DocumentEvent event) { changed(); }
            @Override public void removeUpdate(DocumentEvent event) { changed(); }
            @Override public void changedUpdate(DocumentEvent event) { changed(); }
        };
        queryArea.getDocument().addDocumentListener(staleResults);
        corpusField.getDocument().addDocumentListener(staleResults);
        manifestField.getDocument().addDocumentListener(staleResults);
    }

    private void choose(boolean directory) {
        JFileChooser chooser = new JFileChooser();
        chooser.setDialogTitle(directory ? "Selecionar pasta do corpus" : "Selecionar manifesto C2");
        if (directory)
            chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);
        if (chooser.showOpenDialog(this) == JFileChooser.APPROVE_OPTION) {
            if (directory)
                corpusField.setText(chooser.getSelectedFile().getAbsolutePath());
            else
                manifestField.setText(chooser.getSelectedFile().getAbsolutePath());
        }
    }

    private void cancelPreflight() {
        SwingWorker<C2PreflightRunner.Outcome, Void> worker = activeWorker;
        if (worker == null)
            return;
        // Even a fully calculated result still waiting on the EDT must not reappear.
        cancellationRequested = true;
        inputRevision++;
        resultsArea.setText("Cancelamento solicitado. A consulta não produzirá evidências.");
        stateLabel.setText("Cancelando…");
        cancelButton.setEnabled(false);
        worker.cancel(true);
    }

    private void beginPreflight() {
        if (activeWorker != null || !runButton.isEnabled())
            return;
        String rootSetting = AssistantLaunchSettings.preferLauncherEnvironment(
                System.getenv("JAAMSIM_ASSISTANT_ROOT"),
                System.getProperty("jaamsim.assistant.root"));
        if (rootSetting == null) {
            resultsArea.setText("Bloqueado: defina JAAMSIM_ASSISTANT_ROOT ou -Djaamsim.assistant.root."
                    + " Não buscarei scripts próximos ao modelo .cfg.");
            return;
        }
        final long submittedRevision = inputRevision;
        final String question = queryArea.getText();
        final String corpus = corpusField.getText();
        final String manifest = manifestField.getText();
        final String python = AssistantLaunchSettings.preferLauncherEnvironment(
                System.getenv("JAAMSIM_PYTHON"), System.getProperty("jaamsim.python"));
        final Path root, corpusPath, manifestPath;
        try {
            root = Paths.get(rootSetting);
            corpusPath = Paths.get(corpus);
            manifestPath = Paths.get(manifest);
        }
        catch (RuntimeException error) {
            resultsArea.setText("Bloqueado: informe caminhos válidos para corpus e manifesto.");
            return;
        }
        runButton.setEnabled(false);
        cancelButton.setEnabled(true);
        cancellationRequested = false;
        stateLabel.setText("Verificando fontes locais…");
        resultsArea.setText("Consulta em execução no processo Python local. Nenhum LLM é acionado.");
        activeWorker = new SwingWorker<C2PreflightRunner.Outcome, Void>() {
            @Override
            protected C2PreflightRunner.Outcome doInBackground() throws Exception {
                return C2PreflightRunner.execute(root, corpusPath, manifestPath,
                        question, python == null ? "python" : python);
            }
            @Override
            protected void done() {
                try {
                    if (cancellationRequested || isCancelled()) {
                        resultsArea.setText("Consulta cancelada. Nenhuma evidência foi reutilizada.");
                        stateLabel.setText("Cancelada");
                        return;
                    }
                    C2PreflightRunner.Outcome result = get();
                    if (inputRevision != submittedRevision
                            || !question.equals(queryArea.getText())
                            || !corpus.equals(corpusField.getText())
                            || !manifest.equals(manifestField.getText())) {
                        resultsArea.setText("Resultado descartado: os parâmetros foram alterados durante a consulta.");
                        stateLabel.setText("Descartado — consulte novamente");
                        return;
                    }
                    resultsArea.setText(result.displayText());
                    resultsArea.setCaretPosition(0);
                    stateLabel.setText("Pré-validação concluída — sem LLM");
                }
                catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    resultsArea.setText("Pré-validação interrompida.");
                    stateLabel.setText("Interrompida");
                }
                catch (CancellationException error) {
                    resultsArea.setText("Consulta cancelada. Nenhuma evidência foi reutilizada.");
                    stateLabel.setText("Cancelada");
                }
                catch (ExecutionException error) {
                    Throwable cause = error.getCause();
                    resultsArea.setText(cause != null && cause.getMessage() != null
                            ? cause.getMessage() : "Pré-validação bloqueada.");
                    stateLabel.setText("Bloqueada");
                }
                finally {
                    activeWorker = null;
                    runButton.setEnabled(true);
                    cancelButton.setEnabled(false);
                    cancellationRequested = false;
                }
            }
        };
        activeWorker.execute();
    }
}
