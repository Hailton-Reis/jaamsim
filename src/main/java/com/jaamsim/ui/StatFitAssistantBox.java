/*
 * JaamSim Discrete Event Simulation
 * Copyright (C) 2026 Hailton Santos Reis
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Academic prototype extension: native StatFit-like assistant shell.
 */
package com.jaamsim.ui;

import java.awt.BorderLayout;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Component;
import java.awt.Desktop;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.GridBagConstraints;
import java.awt.GridBagLayout;
import java.awt.GridLayout;
import java.awt.Insets;
import java.awt.RenderingHints;
import java.awt.Toolkit;
import java.awt.datatransfer.StringSelection;
import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JComboBox;
import javax.swing.JFileChooser;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JSplitPane;
import javax.swing.JTabbedPane;
import javax.swing.JTable;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;
import javax.swing.filechooser.FileNameExtensionFilter;
import javax.swing.table.DefaultTableCellRenderer;
import javax.swing.table.DefaultTableModel;
import javax.swing.table.TableColumnModel;

import com.jaamsim.JSON.JSONParser;
import com.jaamsim.JSON.JSONValue;

/**
 * Native shell for the JaamSim academic StatFit-like assistant.
 *
 * This bridge calls the local Python helper and writes reports/snippets without
 * changing the active JaamSim model.
 */
public class StatFitAssistantBox extends FrameBox {

	private static final int STATFIT_TIMEOUT_SECONDS = 60;
	private static final int DATA_ASSIST_TIMEOUT_SECONDS = 90;
	private static final int MAX_PROCESS_OUTPUT_CHARS = 8000;
	private static final Color SURFACE_COLOR = new Color(245, 247, 250);
	private static final Color PANEL_COLOR = new Color(255, 255, 255);
	private static final Color BORDER_COLOR = new Color(205, 211, 218);
	private static final Color ACCENT_COLOR = new Color(40, 112, 86);
	private static final Color SOFT_ACCENT_COLOR = new Color(232, 246, 240);
	private static final Color WARNING_COLOR = new Color(255, 249, 227);

	private static StatFitAssistantBox myInstance;

	private final JTextField dataFileField;
	private final JTextField columnField;
	private final JTextField objectNameField;
	private final JComboBox<String> fitKindCombo;
	private final JComboBox<String> supportCombo;
	private final JTextArea pastedDataArea;
	private final JTextArea statusArea;
	private final JTextArea previewArea;
	private final JTextArea assistArea;
	private final JLabel stateLabel;
	private final JLabel chartStatusLabel;
	private final JComboBox<String> chartDistributionCombo;
	private final JTabbedPane mainTabs;
	private final JTabbedPane inputModeTabs;
	private final DefaultTableModel distributionTableModel;
	private final StatFitChartView histogramView;
	private final StatFitChartView ecdfView;
	private final StatFitChartView qqView;
	private final StatFitChartView ppView;
	private final AtomicLong latestPrepareRequest = new AtomicLong();
	private final AtomicLong latestFitRequest = new AtomicLong();
	private File preparedDataFile;
	private File latestMarkdownReportFile;
	private File latestJsonReportFile;
	private File latestSnippetFile;
	private File latestHistogramFile;
	private File latestEcdfFile;
	private File latestQqFile;
	private File latestPpFile;
	private boolean updatingChartDistributionCombo;

	private StatFitAssistantBox() {
		super("Assistente StatFit");
		setType(Type.NORMAL);
		setAutoRequestFocus(true);
		setDefaultCloseOperation(FrameBox.DISPOSE_ON_CLOSE);
		setPreferredSize(new Dimension(1040, 760));
		getContentPane().setBackground(SURFACE_COLOR);

		dataFileField = new JTextField();
		columnField = new JTextField();
		objectNameField = new JTextField();
		fitKindCombo = new JComboBox<>(new String[] {
				"Continuo (tempos, medidas)",
				"Discreto (contagens/eventos)"
		});
		supportCombo = new JComboBox<>(new String[] {
				"Automatico",
				"Somente positivo",
				"Limitado por mínimo/máximo",
				"Não limitado"
		});

		pastedDataArea = new JTextArea();
		pastedDataArea.setRows(14);
		pastedDataArea.setLineWrap(false);
		pastedDataArea.setTabSize(2);
		pastedDataArea.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12));
		pastedDataArea.setBorder(BorderFactory.createEmptyBorder(6, 6, 6, 6));
		pastedDataArea.setToolTipText("Cole aqui uma coluna do Excel ou um bloco CSV/TXT. Linhas vazias e cabecalhos serao tratados.");

		statusArea = new JTextArea();
		statusArea.setEditable(false);
		statusArea.setLineWrap(true);
		statusArea.setWrapStyleWord(true);
		statusArea.setTabSize(2);
		statusArea.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
		statusArea.setBackground(PANEL_COLOR);
		statusArea.setBorder(BorderFactory.createEmptyBorder(10, 12, 10, 12));

		previewArea = new JTextArea();
		previewArea.setEditable(false);
		previewArea.setLineWrap(true);
		previewArea.setWrapStyleWord(true);
		previewArea.setTabSize(2);
		previewArea.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12));
		previewArea.setBackground(PANEL_COLOR);
		previewArea.setBorder(BorderFactory.createEmptyBorder(10, 12, 10, 12));

		assistArea = new JTextArea();
		assistArea.setEditable(false);
		assistArea.setLineWrap(true);
		assistArea.setWrapStyleWord(true);
		assistArea.setTabSize(2);
		assistArea.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
		assistArea.setBackground(PANEL_COLOR);
		assistArea.setBorder(BorderFactory.createEmptyBorder(10, 12, 10, 12));

		histogramView = new StatFitChartView("Histograma", StatFitChartView.Mode.HISTOGRAM);
		ecdfView = new StatFitChartView("CDF empírica", StatFitChartView.Mode.POINTS);
		qqView = new StatFitChartView("Q-Q", StatFitChartView.Mode.POINTS_WITH_DIAGONAL);
		ppView = new StatFitChartView("P-P", StatFitChartView.Mode.POINTS_WITH_DIAGONAL);
		chartStatusLabel = new JLabel("Rode AutoFit para ver os gráficos aqui dentro do JaamSim.");
		chartStatusLabel.setBorder(BorderFactory.createEmptyBorder(6, 10, 6, 10));
		chartStatusLabel.setOpaque(true);
		chartStatusLabel.setBackground(SOFT_ACCENT_COLOR);
		chartStatusLabel.setForeground(new Color(35, 78, 62));
		chartDistributionCombo = new JComboBox<>();
		chartDistributionCombo.setEnabled(false);
		chartDistributionCombo.setToolTipText("Escolha qual distribuição do ranking será exibida nos gráficos internos.");
		chartDistributionCombo.addActionListener(e -> {
			if (updatingChartDistributionCombo)
				return;
			String distribution = getSelectedChartDistribution();
			if (distribution != null && latestJsonReportFile != null)
				updateEmbeddedChartsFromJson(latestJsonReportFile, distribution);
		});

		distributionTableModel = new DefaultTableModel(new String[] {
				"#", "Distribuição", "Tipo", "KS", "KS crítico", "Decisão", "Aceitação (%)", "AIC", "BIC", "Expressão", "Parâmetros", "Observação"
		}, 0) {
			@Override
			public boolean isCellEditable(int row, int column) {
				return false;
			}
		};

		inputModeTabs = new JTabbedPane();
		mainTabs = new JTabbedPane();
		mainTabs.setBorder(BorderFactory.createEmptyBorder(8, 8, 0, 8));
		mainTabs.addTab("Dados", buildDataTab());
		mainTabs.addTab("Resultados", buildResultsPanel());
		mainTabs.addTab("Gráficos", buildEmbeddedChartsPanel());
		mainTabs.addTab("Avançado", buildAdvancedPanel());

		JPanel topPanel = new JPanel(new BorderLayout());
		topPanel.setBackground(SURFACE_COLOR);
		topPanel.setBorder(BorderFactory.createEmptyBorder(8, 8, 0, 8));
		topPanel.add(buildHeaderPanel(), BorderLayout.CENTER);
		getContentPane().add(topPanel, BorderLayout.NORTH);
		getContentPane().add(mainTabs, BorderLayout.CENTER);

		JPanel bottomPanel = new JPanel(new BorderLayout(8, 0));
		bottomPanel.setBackground(SURFACE_COLOR);
		bottomPanel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

		stateLabel = new JLabel("Pronto para receber dados");
		stateLabel.setOpaque(true);
		stateLabel.setBackground(SOFT_ACCENT_COLOR);
		stateLabel.setForeground(new Color(35, 78, 62));
		stateLabel.setBorder(BorderFactory.createEmptyBorder(6, 10, 6, 10));
		bottomPanel.add(stateLabel, BorderLayout.WEST);

		JLabel hint = new JLabel("Fluxo principal: cole dados, confira tipo/suporte e clique em AutoFit.");
		hint.setForeground(new Color(85, 92, 102));
		bottomPanel.add(hint, BorderLayout.CENTER);
		getContentPane().add(bottomPanel, BorderLayout.SOUTH);

		refreshStatus();
		pack();
	}

	private JPanel buildDataTab() {
		JPanel wrapper = new JPanel(new BorderLayout(8, 8));
		wrapper.setBackground(SURFACE_COLOR);
		wrapper.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

		JPanel selectors = new JPanel(new GridBagLayout());
		selectors.setBackground(PANEL_COLOR);
		selectors.setBorder(BorderFactory.createTitledBorder("Como interpretar os dados"));
		addComboRow(selectors, 0, "Tipo", fitKindCombo);
		addComboRow(selectors, 1, "Suporte", supportCombo);
		wrapper.add(selectors, BorderLayout.NORTH);

		inputModeTabs.addTab("Colar dados", buildPasteInputPanel());
		inputModeTabs.addTab("Anexar arquivo", buildFileInputPanel());
		inputModeTabs.addChangeListener(e -> updateInputModeState());

		JSplitPane split = new JSplitPane(JSplitPane.VERTICAL_SPLIT, inputModeTabs, new JScrollPane(previewArea));
		split.setResizeWeight(0.68);
		split.setBorder(BorderFactory.createEmptyBorder());
		wrapper.add(split, BorderLayout.CENTER);
		return wrapper;
	}

	private JPanel buildPasteInputPanel() {
		JPanel panel = new JPanel(new BorderLayout(8, 8));
		panel.setBackground(PANEL_COLOR);
		panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
		JTextArea guide = createGuideArea(
				"Cole uma coluna do Excel, uma lista de valores ou um bloco CSV/TXT. O modulo ignora cabecalhos, linhas vazias e indices provaveis.");
		panel.add(guide, BorderLayout.NORTH);
		JScrollPane pasteScroll = new JScrollPane(pastedDataArea);
		pasteScroll.setBorder(BorderFactory.createTitledBorder("Dados colados"));
		panel.add(pasteScroll, BorderLayout.CENTER);

		JPanel actions = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
		actions.setOpaque(false);
		JButton runButton = createPrimaryButton("AutoFit",
				"Roda o ajuste e atualiza resultados/gráficos dentro desta janela.");
		runButton.addActionListener(e -> runStatFit());
		JButton previewButton = createActionButton("Pré-visualizar", "Confere a série numérica antes do ajuste.");
		previewButton.addActionListener(e -> previewInputData());
		JButton exampleButton = createActionButton("Ver formato", "Mostra exemplos de entrada aceitos.");
		exampleButton.addActionListener(e -> showExample());
		JButton clearButton = createActionButton("Limpar", "Limpa os dados colados.");
		clearButton.addActionListener(e -> {
			pastedDataArea.setText("");
			previewArea.setText("Cole dados e clique em Pré-visualizar ou AutoFit.");
			updateState("Aguardando dados");
		});
		actions.add(runButton);
		actions.add(previewButton);
		actions.add(exampleButton);
		actions.add(clearButton);
		panel.add(actions, BorderLayout.SOUTH);
		return panel;
	}

	private JPanel buildFileInputPanel() {
		JPanel panel = new JPanel(new BorderLayout(8, 8));
		panel.setBackground(PANEL_COLOR);
		panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

		JPanel formPanel = new JPanel(new GridBagLayout());
		formPanel.setOpaque(false);
		formPanel.setBorder(BorderFactory.createTitledBorder("Arquivo CSV/TXT"));
		addFormRow(formPanel, 0, "Arquivo", dataFileField);
		addFormRow(formPanel, 1, "Coluna numérica", columnField);
		addFormRow(formPanel, 2, "Nome da distribuição", objectNameField);
		JButton browseButton = createActionButton("Procurar", "Escolha um arquivo CSV/TXT com observacoes numericas.");
		browseButton.addActionListener(e -> browseDataFile());
		GridBagConstraints browseConstraints = new GridBagConstraints();
		browseConstraints.gridx = 2;
		browseConstraints.gridy = 0;
		browseConstraints.insets = new Insets(4, 4, 4, 8);
		browseConstraints.fill = GridBagConstraints.HORIZONTAL;
		formPanel.add(browseButton, browseConstraints);
		panel.add(formPanel, BorderLayout.NORTH);

		JTextArea guide = createGuideArea(
				"Use este modo quando os dados estiverem em arquivo. Se houver várias colunas, confirme a coluna numérica antes de rodar AutoFit.");
		panel.add(guide, BorderLayout.CENTER);

		JPanel actions = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
		actions.setOpaque(false);
		JButton runButton = createPrimaryButton("AutoFit", "Roda o ajuste do arquivo selecionado.");
		runButton.addActionListener(e -> runStatFit());
		JButton previewButton = createActionButton("Pré-visualizar", "Mostra colunas e amostra antes do ajuste.");
		previewButton.addActionListener(e -> previewInputData());
		JButton prepareButton = createActionButton("Preparar dados", "Gera CSV limpo e análise de tratamento.");
		prepareButton.addActionListener(e -> runDataAssist());
		JButton usePreparedButton = createActionButton("Usar CSV preparado", "Usa o último CSV limpo gerado pela preparação.");
		usePreparedButton.addActionListener(e -> usePreparedData());
		JButton useExampleButton = createActionButton("Usar exemplo", "Carrega o CSV de demonstração.");
		useExampleButton.addActionListener(e -> useExampleData());
		actions.add(runButton);
		actions.add(previewButton);
		actions.add(prepareButton);
		actions.add(usePreparedButton);
		actions.add(useExampleButton);
		panel.add(actions, BorderLayout.SOUTH);
		return panel;
	}

	private JPanel buildResultsPanel() {
		JPanel panel = new JPanel(new BorderLayout(8, 8));
		panel.setBackground(SURFACE_COLOR);
		panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
		JTable table = new JTable(distributionTableModel);
		table.setAutoResizeMode(JTable.AUTO_RESIZE_OFF);
		table.setFillsViewportHeight(true);
		table.setRowHeight(22);
		table.setDefaultRenderer(Object.class, new DistributionRankingRenderer());
		configureDistributionTableColumns(table);
		table.getSelectionModel().addListSelectionListener(event -> {
			if (event.getValueIsAdjusting())
				return;
			int viewRow = table.getSelectedRow();
			if (viewRow < 0)
				return;
			int modelRow = table.convertRowIndexToModel(viewRow);
			Object value = distributionTableModel.getValueAt(modelRow, 1);
			if (value != null)
				selectChartDistribution(value.toString());
		});
		JScrollPane tableScroll = new JScrollPane(table);
		tableScroll.setBorder(BorderFactory.createTitledBorder("Ranking de distribuições candidatas"));
		JScrollPane summaryScroll = new JScrollPane(statusArea);
		summaryScroll.setBorder(BorderFactory.createTitledBorder("Resumo do ajuste"));
		summaryScroll.setPreferredSize(new Dimension(200, 135));
		JSplitPane split = new JSplitPane(JSplitPane.VERTICAL_SPLIT, tableScroll, summaryScroll);
		split.setResizeWeight(0.82);
		split.setBorder(BorderFactory.createEmptyBorder());
		panel.add(split, BorderLayout.CENTER);
		return panel;
	}

	private static void configureDistributionTableColumns(JTable table) {
		TableColumnModel columns = table.getColumnModel();
		int[] widths = { 42, 130, 92, 82, 90, 110, 110, 88, 88, 220, 260, 360 };
		for (int i = 0; i < widths.length && i < columns.getColumnCount(); i++) {
			columns.getColumn(i).setPreferredWidth(widths[i]);
		}
	}

	private static class DistributionRankingRenderer extends DefaultTableCellRenderer {
		private static final Color ACCEPTED_BACKGROUND = new Color(226, 245, 234);
		private static final Color REJECTED_BACKGROUND = new Color(255, 235, 232);
		private static final Color INCONCLUSIVE_BACKGROUND = new Color(255, 249, 227);
		private static final Color SELECTED_BACKGROUND = new Color(184, 207, 229);

		@Override
		public Component getTableCellRendererComponent(JTable table, Object value, boolean isSelected,
				boolean hasFocus, int row, int column) {
			Component component = super.getTableCellRendererComponent(table, value, isSelected, hasFocus, row, column);
			int modelRow = table.convertRowIndexToModel(row);
			String decision = "";
			if (modelRow >= 0 && modelRow < table.getModel().getRowCount()) {
				Object decisionValue = table.getModel().getValueAt(modelRow, 5);
				decision = decisionValue == null ? "" : decisionValue.toString().toLowerCase(Locale.ROOT);
			}

			if (isSelected) {
				component.setBackground(SELECTED_BACKGROUND);
			}
			else if (decision.contains("não rejeitada") || decision.contains("nao rejeitada")) {
				component.setBackground(ACCEPTED_BACKGROUND);
			}
			else if (decision.contains("rejeitada")) {
				component.setBackground(REJECTED_BACKGROUND);
			}
			else {
				component.setBackground(INCONCLUSIVE_BACKGROUND);
			}

			if (component instanceof JLabel) {
				JLabel label = (JLabel) component;
				label.setToolTipText(value == null ? "" : value.toString());
				label.setFont(label.getFont().deriveFont(column == 5 || column == 6 || column == 9 ? Font.BOLD : Font.PLAIN));
			}
			return component;
		}
	}

	private JPanel buildAdvancedPanel() {
		JPanel panel = new JPanel(new BorderLayout(8, 8));
		panel.setBackground(SURFACE_COLOR);
		panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
		panel.add(new JScrollPane(assistArea), BorderLayout.CENTER);

		JPanel actions = new JPanel(new GridLayout(0, 3, 6, 6));
		actions.setOpaque(false);
		JButton openChartsButton = createActionButton("Abrir SVGs externos", "Opcional: abre os arquivos SVG fora do JaamSim.");
		openChartsButton.addActionListener(e -> openLatestStatFitCharts());
		JButton openReportButton = createActionButton("Abrir relatório", "Abre o relatório Markdown do último ajuste.");
		openReportButton.addActionListener(e -> openLatestStatFitReport());
		JButton copySnippetButton = createActionButton("Copiar distribuição JaamSim (.cfg)",
				"Copia o bloco .cfg sugerido; cole manualmente apenas após revisar.");
		copySnippetButton.addActionListener(e -> copyLatestStatFitSnippet());
		JButton openOutputButton = createActionButton("Abrir pasta de resultados", "Abre a pasta com arquivos gerados.");
		openOutputButton.addActionListener(e -> openStatFitOutputFolder());
		JButton closeButton = createActionButton("Fechar", "Fecha esta janela.");
		closeButton.addActionListener(e -> dispose());
		actions.add(openChartsButton);
		actions.add(openReportButton);
		actions.add(copySnippetButton);
		actions.add(openOutputButton);
		actions.add(closeButton);
		panel.add(actions, BorderLayout.SOUTH);
		return panel;
	}

	private JPanel buildEmbeddedChartsPanel() {
		JPanel wrapper = new JPanel(new BorderLayout(8, 8));
		wrapper.setBackground(SURFACE_COLOR);
		wrapper.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
		JPanel top = new JPanel(new BorderLayout(8, 0));
		top.setOpaque(false);
		top.add(chartStatusLabel, BorderLayout.CENTER);
		JPanel selector = new JPanel(new FlowLayout(FlowLayout.RIGHT, 6, 0));
		selector.setOpaque(false);
		selector.add(new JLabel("Distribuição exibida:"));
		chartDistributionCombo.setPreferredSize(new Dimension(220, 26));
		selector.add(chartDistributionCombo);
		top.add(selector, BorderLayout.EAST);
		wrapper.add(top, BorderLayout.NORTH);

		JPanel charts = new JPanel(new GridLayout(2, 2, 8, 8));
		charts.setOpaque(false);
		charts.add(histogramView);
		charts.add(ecdfView);
		charts.add(qqView);
		charts.add(ppView);
		wrapper.add(charts, BorderLayout.CENTER);
		return wrapper;
	}

	public synchronized static StatFitAssistantBox getInstance() {
		if (myInstance == null)
			myInstance = new StatFitAssistantBox();

		myInstance.refreshStatus();
		return myInstance;
	}

	private synchronized static void killInstance() {
		myInstance = null;
	}

	@Override
	public void dispose() {
		killInstance();
		super.dispose();
	}

	private JPanel buildHeaderPanel() {
		JPanel panel = new JPanel(new BorderLayout(8, 4));
		panel.setBackground(PANEL_COLOR);
		panel.setBorder(BorderFactory.createCompoundBorder(
				BorderFactory.createLineBorder(BORDER_COLOR),
				BorderFactory.createEmptyBorder(10, 12, 10, 12)));

		JLabel title = new JLabel("Ajuste de distribuicoes");
		title.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 15));
		title.setForeground(ACCENT_COLOR);
		panel.add(title, BorderLayout.NORTH);

		JTextArea subtitle = createGuideArea(
				"Cole dados do Excel, selecione um CSV/TXT ou use o exemplo. O módulo limpa a entrada, testa distribuições candidatas e gera relatórios/snippet para revisão.");
		subtitle.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 0));
		panel.add(subtitle, BorderLayout.CENTER);

		JLabel guardrail = new JLabel("Somente leitura: não cria objetos, não altera inputs e não injeta snippet automaticamente.");
		guardrail.setOpaque(true);
		guardrail.setBackground(WARNING_COLOR);
		guardrail.setBorder(BorderFactory.createEmptyBorder(4, 8, 4, 8));
		panel.add(guardrail, BorderLayout.SOUTH);
		return panel;
	}

	private JPanel buildStepPanel() {
		JPanel panel = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 4));
		panel.setOpaque(false);
		panel.add(createStepBadge("1", "Colar ou escolher dados"));
		panel.add(createStepBadge("2", "Confirmar coluna"));
		panel.add(createStepBadge("3", "Pré-visualizar"));
		panel.add(createStepBadge("4", "Ajustar e revisar"));
		panel.add(createStepBadge("5", "Copiar distribuição se fizer sentido"));
		return panel;
	}

	private static JLabel createStepBadge(String number, String text) {
		JLabel label = new JLabel(number + ". " + text);
		label.setOpaque(true);
		label.setBackground(SOFT_ACCENT_COLOR);
		label.setForeground(new Color(35, 78, 62));
		label.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 11));
		label.setBorder(BorderFactory.createEmptyBorder(4, 8, 4, 8));
		return label;
	}

	private static void addFormRow(JPanel panel, int row, String label, JTextField field) {
		JLabel jLabel = new JLabel(label);
		GridBagConstraints labelConstraints = new GridBagConstraints();
		labelConstraints.gridx = 0;
		labelConstraints.gridy = row;
		labelConstraints.insets = new Insets(4, 8, 4, 4);
		labelConstraints.anchor = GridBagConstraints.WEST;
		panel.add(jLabel, labelConstraints);

		GridBagConstraints fieldConstraints = new GridBagConstraints();
		fieldConstraints.gridx = 1;
		fieldConstraints.gridy = row;
		fieldConstraints.weightx = 1.0;
		fieldConstraints.insets = new Insets(4, 4, 4, 4);
		fieldConstraints.fill = GridBagConstraints.HORIZONTAL;
		panel.add(field, fieldConstraints);
	}

	private static void addComboRow(JPanel panel, int row, String label, JComboBox<String> combo) {
		JLabel jLabel = new JLabel(label);
		GridBagConstraints labelConstraints = new GridBagConstraints();
		labelConstraints.gridx = 0;
		labelConstraints.gridy = row;
		labelConstraints.insets = new Insets(4, 8, 4, 4);
		labelConstraints.anchor = GridBagConstraints.WEST;
		panel.add(jLabel, labelConstraints);

		GridBagConstraints fieldConstraints = new GridBagConstraints();
		fieldConstraints.gridx = 1;
		fieldConstraints.gridy = row;
		fieldConstraints.weightx = 1.0;
		fieldConstraints.insets = new Insets(4, 4, 4, 4);
		fieldConstraints.fill = GridBagConstraints.HORIZONTAL;
		panel.add(combo, fieldConstraints);
	}

	private void refreshStatus() {
		StringBuilder sb = new StringBuilder();
		sb.append("Assistente StatFit pronto.").append(System.lineSeparator());
		sb.append(System.lineSeparator());
		sb.append("O que fazer agora:").append(System.lineSeparator());
		sb.append("1. Na aba Dados, cole uma coluna do Excel ou entre em Anexar arquivo.").append(System.lineSeparator());
		sb.append("2. Escolha se a variável é contínua ou discreta e confirme o suporte.").append(System.lineSeparator());
		sb.append("3. Clique em AutoFit. Resultados e gráficos serão atualizados dentro desta janela.").append(System.lineSeparator());
		sb.append("4. Revise o ranking antes de copiar a distribuição JaamSim (.cfg).").append(System.lineSeparator());
		sb.append(System.lineSeparator());
		sb.append("Entrada flexível: coluna colada, cabeçalho, linhas vazias, CSV/TXT e separadores por tab, ponto e vírgula ou vírgula.").append(System.lineSeparator());
		sb.append("Saída: relatório Markdown, JSON e snippet .cfg revisável.");

		statusArea.setText(sb.toString());
		statusArea.setCaretPosition(0);
		previewArea.setText("Cole dados e clique em Pré-visualizar ou AutoFit. Para arquivo, use a subaba Anexar arquivo.");
		previewArea.setCaretPosition(0);
		assistArea.setText("Ações avançadas ficam aqui: preparar dados, abrir arquivos externos, relatório e copiar distribuição .cfg.");
		assistArea.setCaretPosition(0);
		distributionTableModel.setRowCount(0);
		updateState("Pronto para receber dados");
	}

	private static JTextArea createGuideArea(String text) {
		JTextArea area = new JTextArea(cleanDisplayText(text));
		area.setEditable(false);
		area.setLineWrap(true);
		area.setWrapStyleWord(true);
		area.setTabSize(2);
		area.setOpaque(false);
		area.setBorder(BorderFactory.createEmptyBorder(6, 8, 2, 8));
		return area;
	}

	private static JButton createActionButton(String text, String tooltip) {
		JButton button = new JButton(text);
		button.setFocusPainted(false);
		button.setToolTipText(tooltip);
		return button;
	}

	private static JButton createPrimaryButton(String text, String tooltip) {
		JButton button = createActionButton(text, tooltip);
		button.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 12));
		button.setForeground(Color.WHITE);
		button.setBackground(ACCENT_COLOR);
		button.setOpaque(true);
		return button;
	}

	private boolean isFileInputMode() {
		return inputModeTabs != null && inputModeTabs.getSelectedIndex() == 1;
	}

	private void updateInputModeState() {
		if (isFileInputMode())
			updateState("Modo arquivo: selecione CSV/TXT e confirme a coluna");
		else
			updateState("Modo colagem: cole dados e rode AutoFit");
	}

	private void useExampleData() {
		try {
			Path assistantRoot = findAssistantRoot(new File("."));
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Usar exemplo: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			Path exampleCsv = assistantRoot.resolve("examples")
					.resolve("statfit")
					.resolve("exemplo_dados_tempos.csv");
			if (!Files.isRegularFile(exampleCsv)) {
				appendStatusText(System.lineSeparator()
						+ "Usar exemplo: CSV de exemplo não encontrado: "
						+ exampleCsv.toAbsolutePath() + System.lineSeparator());
				return;
			}

			dataFileField.setText(exampleCsv.toAbsolutePath().toString());
			columnField.setText("tempo_atendimento");
			objectNameField.setText("TempoAtendimentoDemo");
			inputModeTabs.setSelectedIndex(1);
			appendStatusText(System.lineSeparator()
					+ "Usar exemplo: arquivo, coluna e objeto foram preenchidos." + System.lineSeparator());
			previewInputData();
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao usar exemplo: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private void browseDataFile() {
		JFileChooser chooser = new JFileChooser();
		chooser.setFileFilter(new FileNameExtensionFilter("Arquivos de dados CSV/TXT", "csv", "txt"));
		int result = chooser.showOpenDialog(this);
		if (result == JFileChooser.APPROVE_OPTION) {
			dataFileField.setText(chooser.getSelectedFile().getAbsolutePath());
			inputModeTabs.setSelectedIndex(1);
			previewInputData();
		}
	}

	private void showExample() {
		StringBuilder sb = new StringBuilder();
		sb.append("Exemplo aceito:").append(System.lineSeparator());
		sb.append(System.lineSeparator());
		sb.append("tempo_atendimento").append(System.lineSeparator());
		sb.append("4.2").append(System.lineSeparator());
		sb.append("5.1").append(System.lineSeparator());
		sb.append("4.8").append(System.lineSeparator());
		sb.append("6.0").append(System.lineSeparator());
		sb.append("5.4").append(System.lineSeparator());
		sb.append(System.lineSeparator());
		sb.append("Use Coluna numérica = tempo_atendimento quando o CSV tiver várias colunas.").append(System.lineSeparator());
		sb.append("Também é possível colar diretamente uma coluna do Excel na área 'Colar dados'.").append(System.lineSeparator());
			sb.append("O snippet .cfg gerado é uma sugestão para revisão, não uma edição automática do modelo.");
		statusArea.setText(sb.toString());
		statusArea.setCaretPosition(0);
	}

	private void previewInputData() {
		try {
			updateState("Pre-visualizando dados...");
			String rawText = collectInputTextForPreview();
			if (rawText.trim().isEmpty()) {
				previewArea.setText("Nenhum dado encontrado. Cole uma coluna do Excel ou escolha um CSV/TXT.");
				updateState("Aguardando dados");
				return;
			}

			String preview = buildPreviewReport(rawText, columnField.getText().trim());
			previewArea.setText(preview);
			previewArea.setCaretPosition(0);
			appendStatusText(System.lineSeparator()
					+ "StatFit: pré-visualização atualizada. Confira a aba 'Prévia dos dados' antes de ajustar."
					+ System.lineSeparator());
			updateState("Prévia pronta");
		}
		catch (Exception ex) {
			previewArea.setText("Erro na pré-visualização: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage());
			updateState("Erro na prévia");
		}
	}

	private String collectInputTextForPreview() throws IOException {
		String pastedText = isFileInputMode() ? "" : pastedDataArea.getText().trim();
		if (!isFileInputMode() && !pastedText.isEmpty())
			return pastedText;

		String dataFileText = dataFileField.getText().trim();
		if (dataFileText.isEmpty())
			return "";

		Path dataPath = Paths.get(dataFileText);
		if (!Files.isRegularFile(dataPath))
			throw new IOException("arquivo de dados não encontrado: " + dataPath.toAbsolutePath());

		byte[] bytes = Files.readAllBytes(dataPath);
		return new String(bytes, StandardCharsets.UTF_8);
	}

	private static String buildPreviewReport(String rawText, String requestedColumn) {
		String[] rawLines = rawText.split("\\R");
		ArrayList<String[]> rows = new ArrayList<>();
		int emptyLines = 0;
		int maxColumns = 0;

		for (String line : rawLines) {
			if (line.trim().isEmpty()) {
				emptyLines++;
				continue;
			}
			String[] columns = splitPreviewColumns(line);
			rows.add(columns);
			if (columns.length > maxColumns)
				maxColumns = columns.length;
		}

		StringBuilder sb = new StringBuilder();
		sb.append("Prévia local dos dados").append(System.lineSeparator());
		sb.append("----------------------").append(System.lineSeparator());
		sb.append("Linhas lidas: ").append(rawLines.length).append(System.lineSeparator());
		sb.append("Linhas vazias ignoradas: ").append(emptyLines).append(System.lineSeparator());
		sb.append("Linhas úteis: ").append(rows.size()).append(System.lineSeparator());
		sb.append("Colunas detectadas: ").append(maxColumns).append(System.lineSeparator());

		if (rows.isEmpty()) {
			sb.append(System.lineSeparator()).append("Nenhuma linha útil encontrada.");
			return sb.toString();
		}

		boolean hasHeader = looksLikeHeader(rows.get(0));
		String[] header = hasHeader ? rows.get(0) : null;
		int startRow = hasHeader ? 1 : 0;
		int selectedColumn = choosePreviewColumn(rows, header, startRow, requestedColumn, maxColumns);
		ColumnPreviewStats[] stats = buildColumnStats(rows, startRow, maxColumns);

		sb.append("Cabeçalho detectado: ").append(hasHeader ? "sim" : "não").append(System.lineSeparator());
		sb.append("Coluna selecionada: ").append(formatColumnName(header, selectedColumn)).append(System.lineSeparator());
		if (!requestedColumn.isEmpty())
			sb.append("Coluna solicitada: ").append(requestedColumn).append(System.lineSeparator());

		ColumnPreviewStats selectedStats = stats[selectedColumn];
		sb.append("Valores numericos na coluna: ").append(selectedStats.numericCount).append(System.lineSeparator());
		sb.append("Valores não numéricos/ignorados na coluna: ").append(selectedStats.invalidCount).append(System.lineSeparator());

		if (selectedStats.numericCount > 0) {
			sb.append("Mínimo: ").append(formatNumber(selectedStats.min)).append(System.lineSeparator());
			sb.append("Máximo: ").append(formatNumber(selectedStats.max)).append(System.lineSeparator());
			sb.append("Média aproximada: ").append(formatNumber(selectedStats.sum / selectedStats.numericCount)).append(System.lineSeparator());
		}

		sb.append(System.lineSeparator());
		sb.append("Colunas candidatas").append(System.lineSeparator());
		sb.append("------------------").append(System.lineSeparator());
		for (int i = 0; i < stats.length; i++) {
			if (stats[i].numericCount == 0 && stats[i].invalidCount == 0)
				continue;
			sb.append(formatColumnName(header, i))
					.append(" -> numericos=")
					.append(stats[i].numericCount)
					.append(", ignorados=")
					.append(stats[i].invalidCount)
					.append(System.lineSeparator());
		}

		sb.append(System.lineSeparator());
		sb.append("Amostra da coluna selecionada").append(System.lineSeparator());
		sb.append("-----------------------------").append(System.lineSeparator());
		int shown = 0;
		for (int rowIndex = startRow; rowIndex < rows.size() && shown < 15; rowIndex++) {
			String[] row = rows.get(rowIndex);
			if (selectedColumn >= row.length)
				continue;
			Double value = parsePreviewNumber(row[selectedColumn]);
			if (value == null)
				continue;
			sb.append(shown + 1).append(". ").append(formatNumber(value.doubleValue())).append(System.lineSeparator());
			shown++;
		}

		sb.append(System.lineSeparator());
		sb.append("Leitura").append(System.lineSeparator());
		sb.append("-------").append(System.lineSeparator());
		if (selectedStats.numericCount < 5) {
			sb.append("- Há poucos valores numéricos. O ajuste pode ser fraco ou apenas demonstrativo.").append(System.lineSeparator());
		}
		if (maxColumns > 1 && requestedColumn.isEmpty()) {
			sb.append("- Foram detectadas várias colunas. Se a escolha automática não estiver correta, preencha o campo Coluna com o nome do cabeçalho ou número da coluna.").append(System.lineSeparator());
		}
		if (selectedStats.invalidCount > 0) {
			sb.append("- Existem valores ignorados na coluna selecionada. Confira se há texto, unidade, célula mesclada ou total no meio da amostra.").append(System.lineSeparator());
		}
		sb.append("- Esta pré-visualização não altera dados nem modelo; ela apenas antecipa o que será enviado ao ajuste.").append(System.lineSeparator());
		return sb.toString();
	}

	private static String[] splitPreviewColumns(String line) {
		String trimmed = line.trim();
		String delimiter = null;
		if (trimmed.indexOf('\t') >= 0)
			delimiter = "\\t";
		else if (trimmed.indexOf(';') >= 0)
			delimiter = ";";
		else if (trimmed.indexOf(',') >= 0 && !looksLikeDecimalComma(trimmed))
			delimiter = ",";

		if (delimiter == null)
			return new String[] { trimmed };

		String[] parts = trimmed.split(delimiter, -1);
		for (int i = 0; i < parts.length; i++)
			parts[i] = stripPreviewToken(parts[i]);
		return parts;
	}

	private static boolean looksLikeDecimalComma(String text) {
		return text.matches("[+-]?\\d+,\\d+");
	}

	private static String stripPreviewToken(String token) {
		String value = token.trim();
		if (value.startsWith("\"") && value.endsWith("\"") && value.length() > 1)
			value = value.substring(1, value.length() - 1).trim();
		return value;
	}

	private static boolean looksLikeHeader(String[] row) {
		int textCount = 0;
		int numericCount = 0;
		for (String cell : row) {
			if (cell.trim().isEmpty())
				continue;
			if (parsePreviewNumber(cell) == null)
				textCount++;
			else
				numericCount++;
		}
		return textCount > 0 && numericCount == 0;
	}

	private static int choosePreviewColumn(ArrayList<String[]> rows, String[] header, int startRow,
			String requestedColumn, int maxColumns) {
		if (maxColumns <= 1)
			return 0;

		if (!requestedColumn.isEmpty()) {
			int requested = findRequestedColumn(header, requestedColumn, maxColumns);
			if (requested >= 0)
				return requested;
		}

		ColumnPreviewStats[] stats = buildColumnStats(rows, startRow, maxColumns);
		int bestIndex = 0;
		int bestCount = -1;
		for (int i = 0; i < stats.length; i++) {
			if (stats[i].numericCount > bestCount) {
				bestIndex = i;
				bestCount = stats[i].numericCount;
			}
		}
		return bestIndex;
	}

	private static int findRequestedColumn(String[] header, String requestedColumn, int maxColumns) {
		String normalized = requestedColumn.trim().toLowerCase(Locale.ROOT);
		try {
			int oneBased = Integer.parseInt(normalized);
			if (oneBased >= 1 && oneBased <= maxColumns)
				return oneBased - 1;
		}
		catch (NumberFormatException ignored) {
			// Fall through to header matching.
		}

		if (header == null)
			return -1;

		for (int i = 0; i < header.length; i++) {
			if (header[i].trim().toLowerCase(Locale.ROOT).equals(normalized))
				return i;
		}
		return -1;
	}

	private static ColumnPreviewStats[] buildColumnStats(ArrayList<String[]> rows, int startRow, int maxColumns) {
		ColumnPreviewStats[] stats = new ColumnPreviewStats[maxColumns];
		for (int i = 0; i < maxColumns; i++)
			stats[i] = new ColumnPreviewStats();

		for (int rowIndex = startRow; rowIndex < rows.size(); rowIndex++) {
			String[] row = rows.get(rowIndex);
			for (int col = 0; col < maxColumns; col++) {
				String cell = col < row.length ? row[col] : "";
				if (cell.trim().isEmpty())
					continue;
				Double value = parsePreviewNumber(cell);
				if (value == null) {
					stats[col].invalidCount++;
					continue;
				}
				stats[col].add(value.doubleValue());
			}
		}
		return stats;
	}

	private static Double parsePreviewNumber(String raw) {
		String value = stripPreviewToken(raw);
		if (value.isEmpty())
			return null;
		value = value.replace(" ", "");
		if (value.indexOf(',') >= 0 && value.indexOf('.') < 0)
			value = value.replace(',', '.');
		try {
			return Double.valueOf(value);
		}
		catch (NumberFormatException ex) {
			return null;
		}
	}

	private static String formatColumnName(String[] header, int columnIndex) {
		if (header != null && columnIndex < header.length && !header[columnIndex].trim().isEmpty())
			return header[columnIndex].trim() + " (coluna " + (columnIndex + 1) + ")";
		return "coluna " + (columnIndex + 1);
	}

	private static String formatNumber(double value) {
		if (Math.abs(value) >= 1000000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001))
			return String.format(Locale.ROOT, "%.6e", value);
		return String.format(Locale.ROOT, "%.6f", value).replaceAll("0+$", "").replaceAll("\\.$", "");
	}

	private static class ColumnPreviewStats {
		int numericCount;
		int invalidCount;
		double sum;
		double min = Double.POSITIVE_INFINITY;
		double max = Double.NEGATIVE_INFINITY;

		void add(double value) {
			numericCount++;
			sum += value;
			if (value < min)
				min = value;
			if (value > max)
				max = value;
		}
	}

	private void runDataAssist() {
		long request = latestPrepareRequest.incrementAndGet();
		preparedDataFile = null;
		appendAssistText(System.lineSeparator() + "Preparação: analisando dados..." + System.lineSeparator());

		Thread worker = new Thread(() -> runDataAssistWorker(request), "JaamSim StatFit Data Assist");
		worker.setDaemon(true);
		worker.start();
	}

	private void runDataAssistWorker(long request) {
		try {
			updateState("Preparando dados...");
			boolean fileMode = isFileInputMode();
			String dataFileText = fileMode ? dataFileField.getText().trim() : "";
			String pastedText = fileMode ? "" : pastedDataArea.getText().trim();
			if (dataFileText.isEmpty() && pastedText.isEmpty()) {
				appendAssistText("Preparação: cole dados ou escolha um arquivo CSV/TXT primeiro." + System.lineSeparator());
				updateState("Aguardando dados");
				return;
			}

			File anchorFile = dataFileText.isEmpty() ? new File(".") : new File(dataFileText);
			File dataFile = null;
			if (pastedText.isEmpty())
				dataFile = new File(dataFileText);
			if (pastedText.isEmpty() && !dataFile.isFile()) {
				appendAssistText("Preparação: arquivo de dados não encontrado: "
						+ dataFile.getAbsolutePath() + System.lineSeparator());
				updateState("Arquivo não encontrado");
				return;
			}

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendAssistText("Preparação: pasta da extensao academica não encontrada." + System.lineSeparator()
						+ "Configure JAAMSIM_ASSISTANT_ROOT ou jaamsim.assistant.root apontando para extensions/academic-assistant." + System.lineSeparator());
				updateState("Raiz da extensão não encontrada");
				return;
			}

			Path script = assistantRoot.resolve("python").resolve("statfit_data_assist.py");
			if (!Files.isRegularFile(script)) {
				appendAssistText("Preparação: script não encontrado: "
						+ script.toAbsolutePath() + System.lineSeparator());
				updateState("Script não encontrado");
				return;
			}
			Path outputDir = StatFitRunArtifacts.createRunDirectory(
					assistantRoot.resolve("output").resolve("statfit"), "prepare");

			if (!pastedText.isEmpty())
				dataFile = writePastedDataFile(outputDir, pastedText).toFile();

			List<String> command = buildDataAssistCommand(dataFile, script, outputDir);
			appendAssistText(System.lineSeparator()
					+ "Preparação: gerando CSV limpo e análise assistida..." + System.lineSeparator()
					+ "- Origem: " + (pastedText.isEmpty() ? "arquivo selecionado" : "dados colados") + System.lineSeparator()
					+ "- Arquivo de trabalho: " + dataFile.getName() + System.lineSeparator()
					+ "- Pasta de saída: " + outputDir.toAbsolutePath() + System.lineSeparator());

			StatFitRunResult result = executeCommand(command, assistantRoot, DATA_ASSIST_TIMEOUT_SECONDS);
			if (request != latestPrepareRequest.get()) {
				appendAssistText("Preparação anterior preservada em " + outputDir
						+ ", mas não adotada porque uma nova preparação foi iniciada."
						+ System.lineSeparator());
				return;
			}
			StatFitRunArtifacts.Prepared verified = null;
			String validationError = null;
			if (result.finished && result.exitCode == 0) {
				try {
					StatFitRunArtifacts.Prepared candidate =
							StatFitRunArtifacts.validatePreparation(outputDir, result.output);
					StatFitRunArtifacts.recordAcceptedRun(outputDir, candidate);
					verified = candidate;
				}
				catch (IOException ex) {
					validationError = ex.getMessage();
				}
			}
			StringBuilder sb = new StringBuilder();
			sb.append(System.lineSeparator());
			sb.append("Análise de preparação").append(System.lineSeparator());
			sb.append("---------------------").append(System.lineSeparator());
			sb.append("Finalizado: ").append(result.finished ? "sim" : "não").append(System.lineSeparator());
			sb.append("Código de saída: ").append(result.exitCode).append(System.lineSeparator());
			if (!result.finished) {
				sb.append("Preparação: tempo limite após ");
				sb.append(DATA_ASSIST_TIMEOUT_SECONDS);
				sb.append(" segundos. O processo foi interrompido.");
				sb.append(System.lineSeparator());
			}
			appendDataAssistSummary(sb, result.output);
			if (!result.output.trim().isEmpty()) {
				sb.append(System.lineSeparator()).append("Detalhes técnicos").append(System.lineSeparator());
				sb.append("----------------").append(System.lineSeparator());
				sb.append(limitOutput(result.output, MAX_PROCESS_OUTPUT_CHARS)).append(System.lineSeparator());
			}
			if (verified != null) {
				preparedDataFile = verified.csv;
				latestMarkdownReportFile = verified.markdown;
				sb.append("Preparação confirmada nesta execução: ")
						.append(verified.csv.getAbsolutePath()).append(System.lineSeparator());
				sb.append("Revise o CSV e clique em Usar CSV preparado se concordar.")
						.append(System.lineSeparator());
			}
			else {
				sb.append("Preparação não confirmada; arquivos desta execução não serão adotados.")
						.append(System.lineSeparator());
				if (validationError != null)
					sb.append("Motivo: ").append(validationError).append(System.lineSeparator());
			}
			appendAssistText(sb.toString());
			updateState(verified != null ? "Dados preparados" : "Verifique a preparação");
		}
		catch (Exception ex) {
			appendAssistText("Erro na preparação: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
			updateState("Erro na preparação");
		}
	}

	private void appendDataAssistSummary(StringBuilder sb, String output) {
		String column = extractOutputValue(output, "Coluna preparada:");
		String sample = extractOutputValue(output, "Amostra:");
		String quality = extractOutputValue(output, "Classificação preparação:", "Classificacao preparacao:");
		String outliers = extractOutputValue(output, "Outliers IQR:");
		String ignored = extractOutputValue(output, "Valores ignorados:");
		String online = extractOutputValue(output, "IA online:");
		String provider = extractOutputValue(output, "Provedor:");
		String cleanCsv = extractOutputValue(output, "CSV limpo:");
		String markdown = extractOutputValue(output, "Relatório Markdown:", "Relatorio Markdown:");
		String json = extractOutputValue(output, "Relatório JSON:", "Relatorio JSON:");

		if (column != null)
			sb.append("Coluna preparada: ").append(column).append(System.lineSeparator());
		if (sample != null)
			sb.append("Amostra: ").append(sample).append(System.lineSeparator());
		if (quality != null)
			sb.append("Qualidade local: ").append(quality).append(System.lineSeparator());
		if (outliers != null)
			sb.append("Possíveis outliers por IQR: ").append(outliers).append(System.lineSeparator());
		if (ignored != null)
			sb.append("Valores ignorados: ").append(ignored).append(System.lineSeparator());
		if (online != null)
			sb.append("IA online usada: ").append(online).append(System.lineSeparator());
		if (provider != null)
			sb.append("Provedor: ").append(provider).append(System.lineSeparator());
		if (cleanCsv != null)
			sb.append("CSV informado pelo processo: ").append(cleanCsv).append(System.lineSeparator());
		if (markdown != null)
			sb.append("Relatório informado pelo processo: ").append(markdown).append(System.lineSeparator());
		if (json != null)
			sb.append("Auditoria JSON: ").append(json).append(System.lineSeparator());
	}

	private void usePreparedData() {
		if (preparedDataFile == null || !preparedDataFile.isFile()) {
			appendAssistText(System.lineSeparator()
					+ "Usar CSV preparado: ainda não há CSV preparado válido. Clique em Preparar dados primeiro."
					+ System.lineSeparator());
			updateState("Sem CSV preparado");
			return;
		}

		dataFileField.setText(preparedDataFile.getAbsolutePath());
		pastedDataArea.setText("");
		inputModeTabs.setSelectedIndex(1);
		appendAssistText(System.lineSeparator()
				+ "Usar CSV preparado: entrada atualizada para "
				+ preparedDataFile.getAbsolutePath()
				+ System.lineSeparator());
		appendStatusText(System.lineSeparator()
				+ "StatFit: CSV preparado selecionado por ação humana. Confira a prévia antes de ajustar."
				+ System.lineSeparator());
		previewInputData();
		updateState("CSV preparado selecionado");
	}

	private void runStatFit() {
		long request = latestFitRequest.incrementAndGet();
		latestJsonReportFile = null;
		latestSnippetFile = null;
		latestHistogramFile = null;
		latestEcdfFile = null;
		latestQqFile = null;
		latestPpFile = null;
		appendStatusText(System.lineSeparator() + System.lineSeparator()
				+ "StatFit: iniciando ajuste offline..." + System.lineSeparator());

		Thread worker = new Thread(() -> runStatFitWorker(request), "JaamSim StatFit Assistant");
		worker.setDaemon(true);
		worker.start();
	}

	private void runStatFitWorker(long request) {
		try {
			updateState("Preparando dados...");
			boolean fileMode = isFileInputMode();
			String dataFileText = fileMode ? dataFileField.getText().trim() : "";
			String pastedText = fileMode ? "" : pastedDataArea.getText().trim();
			if (dataFileText.isEmpty() && pastedText.isEmpty()) {
				appendStatusText("StatFit: cole dados na aba Dados ou selecione um CSV/TXT em Anexar arquivo." + System.lineSeparator());
				updateState("Aguardando dados");
				return;
			}
			if (fileMode && columnField.getText().trim().isEmpty()) {
				appendStatusText("StatFit: confirme a coluna numérica antes de rodar AutoFit com arquivo." + System.lineSeparator());
				SwingUtilities.invokeLater(() -> mainTabs.setSelectedIndex(0));
				updateState("Informe a coluna numérica");
				return;
			}

			File anchorFile = dataFileText.isEmpty() ? new File(".") : new File(dataFileText);
			File dataFile = null;
			if (pastedText.isEmpty()) {
				dataFile = new File(dataFileText);
			}
			if (pastedText.isEmpty() && !dataFile.isFile()) {
				appendStatusText("StatFit: arquivo de dados não encontrado: "
						+ dataFile.getAbsolutePath() + System.lineSeparator());
				updateState("Arquivo não encontrado");
				return;
			}

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText("StatFit: pasta da extensao academica não encontrada." + System.lineSeparator()
						+ "Configure JAAMSIM_ASSISTANT_ROOT ou jaamsim.assistant.root apontando para extensions/academic-assistant." + System.lineSeparator());
				updateState("Raiz da extensão não encontrada");
				return;
			}

			Path script = assistantRoot.resolve("python").resolve("statfit_auxiliar.py");
			if (!Files.isRegularFile(script)) {
				appendStatusText("StatFit: script não encontrado: " + script + System.lineSeparator());
				updateState("Script não encontrado");
				return;
			}
			Path outputDir = StatFitRunArtifacts.createRunDirectory(
					assistantRoot.resolve("output").resolve("statfit"), "fit");
			if (!pastedText.isEmpty())
				dataFile = writePastedDataFile(outputDir, pastedText).toFile();
			List<String> command = buildStatFitCommand(dataFile, script, outputDir);

			appendStatusText(System.lineSeparator()
					+ "StatFit: preparando ajuste..." + System.lineSeparator()
					+ "- Origem: " + (pastedText.isEmpty() ? "arquivo selecionado" : "dados colados") + System.lineSeparator()
					+ "- Arquivo de trabalho: " + dataFile.getName() + System.lineSeparator()
					+ "- Tipo de dado: " + fitKindCombo.getSelectedItem() + System.lineSeparator()
					+ "- Suporte: " + supportCombo.getSelectedItem() + System.lineSeparator()
					+ "- Pasta de saída: " + outputDir.toAbsolutePath() + System.lineSeparator());
			updateState("Ajustando distribuicoes...");

			StatFitRunResult result = executeCommand(command, assistantRoot, STATFIT_TIMEOUT_SECONDS);
			if (request != latestFitRequest.get()) {
				appendStatusText("Resultado anterior preservado em " + outputDir
						+ ", mas não adotado porque um novo ajuste foi iniciado."
						+ System.lineSeparator());
				return;
			}
			StatFitRunArtifacts.Fit verified = null;
			String validationError = null;
			if (result.finished && result.exitCode == 0) {
				try {
					StatFitRunArtifacts.Fit candidate =
							StatFitRunArtifacts.validateFit(outputDir, result.output);
					StatFitRunArtifacts.recordAcceptedRun(outputDir, candidate);
					verified = candidate;
				}
				catch (IOException ex) {
					validationError = ex.getMessage();
				}
			}
			StringBuilder summary = new StringBuilder();
			summary.append(System.lineSeparator());
			summary.append("Resultado do ajuste").append(System.lineSeparator());
			summary.append("-------------------").append(System.lineSeparator());
			summary.append("Finalizado: ").append(result.finished ? "sim" : "não").append(System.lineSeparator());
			summary.append("Código de saída: ").append(result.exitCode).append(System.lineSeparator());
			if (!result.finished) {
				summary.append("StatFit: tempo limite após ");
				summary.append(STATFIT_TIMEOUT_SECONDS);
				summary.append(" segundos. O processo foi interrompido.");
				summary.append(System.lineSeparator());
			}
			appendReadableResultSummary(summary, result.output);
			if (verified == null) {
				summary.append("Resultado não confirmado: os arquivos desta execução não serão carregados.")
						.append(System.lineSeparator());
				if (validationError != null)
					summary.append("Motivo: ").append(validationError).append(System.lineSeparator());
			}
			else {
				latestMarkdownReportFile = verified.markdown;
				latestJsonReportFile = verified.json;
				latestHistogramFile = verified.histogram;
				latestEcdfFile = verified.ecdf;
				latestQqFile = verified.qq;
				latestPpFile = verified.pp;
				latestSnippetFile = verified.snippet;
				updateDistributionTableFromJson(verified.json);
				updateEmbeddedChartsFromJson(verified.json,
						extractOutputValue(result.output, "Melhor distribuição:", "Melhor distribuicao:"));
				summary.append("Arquivos de uma única execução conferidos: ")
						.append(outputDir.toAbsolutePath()).append(System.lineSeparator());
			}
			appendStatusText(summary.toString());
			StringBuilder details = new StringBuilder();
			details.append(System.lineSeparator()).append("Detalhes técnicos do último AutoFit").append(System.lineSeparator());
			details.append("--------------------------------").append(System.lineSeparator());
			details.append("Finalizado: ").append(result.finished ? "sim" : "não").append(System.lineSeparator());
			details.append("Código de saída: ").append(result.exitCode).append(System.lineSeparator());
			details.append(result.output.trim().isEmpty()
					? "Saída vazia"
					: limitOutput(result.output, MAX_PROCESS_OUTPUT_CHARS));
			details.append(System.lineSeparator());
			appendAssistText(details.toString());
			if (verified != null) {
				SwingUtilities.invokeLater(() -> mainTabs.setSelectedIndex(1));
				updateState("Ajuste concluido");
			}
			else {
				updateState("Verifique os avisos");
			}
		}
		catch (Exception ex) {
			appendStatusText("Erro StatFit: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
			updateState("Erro no ajuste");
		}
	}

	private void appendReadableResultSummary(StringBuilder sb, String output) {
		String best = extractOutputValue(output, "Melhor distribuição:", "Melhor distribuicao:");
		String quality = extractOutputValue(output, "Classificação qualidade:", "Classificacao qualidade:");
		String iqr = extractOutputValue(output, "IQR:");
		String outliers = extractOutputValue(output, "Outliers IQR:");
		String markdown = extractOutputValue(output, "Relatório Markdown:", "Relatorio Markdown:");
		String json = extractOutputValue(output, "Relatório JSON:", "Relatorio JSON:");
		String histogram = extractOutputValue(output, "Gráfico histograma:", "Grafico histograma:");
		String ecdf = extractOutputValue(output, "Gráfico CDF empírica:", "Grafico CDF empirica:");
		String qq = extractOutputValue(output, "Gráfico Q-Q:", "Grafico Q-Q:");
		String pp = extractOutputValue(output, "Gráfico P-P:", "Grafico P-P:");
		String snippet = extractOutputValue(output, "Snippet JaamSim:");

		if (best != null) {
			sb.append("Melhor candidata: ").append(best).append(System.lineSeparator());
			sb.append("Interpretação: use como hipótese inicial, não como decisão automática. Compare com o processo real antes de aplicar.").append(System.lineSeparator());
		}
		if (quality != null)
			sb.append("Qualidade local: ").append(quality).append(System.lineSeparator());
		if (iqr != null)
			sb.append("IQR: ").append(iqr).append(System.lineSeparator());
		if (outliers != null)
			sb.append("Possíveis outliers por IQR: ").append(outliers).append(System.lineSeparator());
		// Parsed paths are display-only. A completed run is adopted only
		// after StatFitRunArtifacts validates the JSON, SVGs and snippet.
		if (markdown != null)
			sb.append("Relatório informado: ").append(markdown).append(System.lineSeparator());
		if (json != null)
			sb.append("JSON informado: ").append(json).append(System.lineSeparator());
		if (histogram != null && ecdf != null && qq != null && pp != null)
			sb.append("Gráficos informados pelo processo: 4").append(System.lineSeparator());
		if (snippet != null)
			sb.append("Snippet informado: ").append(snippet).append(System.lineSeparator());

		if (best != null) {
			sb.append("Próximo passo: confira o ranking e a aba Gráficos. Use Copiar distribuição JaamSim (.cfg) somente se a candidata fizer sentido para o processo real.").append(System.lineSeparator());
		}
	}

	private static String extractOutputValue(String output, String... prefixes) {
		String[] lines = output.split("\\R");
		for (String line : lines) {
			String trimmed = line.trim();
			for (String prefix : prefixes) {
				if (trimmed.startsWith(prefix))
					return trimmed.substring(prefix.length()).trim();
			}
		}
		return null;
	}

	private void updateState(final String text) {
		SwingUtilities.invokeLater(() -> stateLabel.setText(text));
	}

	private Path writePastedDataFile(Path outputDir, String pastedText) throws IOException {
		Files.createDirectories(outputDir);
		Path pastedFile = outputDir.resolve("statfit_pasted_input_" + System.currentTimeMillis() + ".txt");
		Files.write(pastedFile, pastedText.getBytes(StandardCharsets.UTF_8));
		return pastedFile;
	}

	private void openStatFitOutputFolder() {
		try {
			File anchorFile = new File(".");
			String dataFileText = dataFileField.getText().trim();
			if (!dataFileText.isEmpty())
				anchorFile = new File(dataFileText);

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir resultados: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			Path outputDir = assistantRoot.resolve("output")
					.resolve("statfit");
			openFolder(outputDir, "Abrir resultados StatFit");
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao abrir resultados: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private void updateEmbeddedChartsFromJson(File jsonFile, String selectedDistribution) {
		try {
			if (jsonFile == null || !jsonFile.isFile()) {
				updateChartStatus("Gráficos: relatório JSON ainda não encontrado.");
				return;
			}
			JSONValue root = JSONParser.parse(new String(Files.readAllBytes(jsonFile.toPath()), StandardCharsets.UTF_8));
			List<double[]> histogram = readPointList(root, "histogram", "lower", "count");
			List<double[]> cdf = readPointList(root, "empirical_cdf", "x", "probability");
			String distribution = selectedDistribution != null && !selectedDistribution.trim().isEmpty()
					? selectedDistribution
					: getStringChild(root, "best_distribution", "");
			JSONValue selectedCandidate = findCandidate(root, distribution);
			if (selectedCandidate == null) {
				selectedCandidate = firstCandidate(root);
				distribution = selectedCandidate == null ? "candidata" : getStringChild(selectedCandidate, "distribution", "candidata");
			}
			List<double[]> qq = readDiagnosticPointList(root, distribution, "qq_points", "theoretical", "observed");
			List<double[]> pp = readDiagnosticPointList(root, distribution, "pp_points", "theoretical", "empirical");
			if (qq.isEmpty())
				qq = readPointList(root, "qq_points", "theoretical", "observed");
			if (pp.isEmpty())
				pp = readPointList(root, "pp_points", "theoretical", "empirical");
			FitCurve curve = readFitCurve(selectedCandidate);
			final String chartDistribution = distribution;
			final List<double[]> histogramPoints = histogram;
			final List<double[]> cdfPoints = cdf;
			final List<double[]> qqPoints = qq;
			final List<double[]> ppPoints = pp;
			final FitCurve selectedCurve = curve;
			SwingUtilities.invokeLater(() -> {
				histogramView.setData(histogramPoints);
				histogramView.setCurve(selectedCurve);
				ecdfView.setData(cdfPoints);
				qqView.setData(qqPoints);
				ppView.setData(ppPoints);
				chartStatusLabel.setText("Gráficos exibidos para: " + chartDistribution
						+ ". Compare visualmente antes de copiar a distribuição .cfg.");
			});
		}
		catch (Exception ex) {
			updateChartStatus("Gráficos: não consegui ler o JSON do último ajuste (" + ex.getClass().getSimpleName() + ").");
		}
	}

	private void updateDistributionTableFromJson(File jsonFile) {
		try {
			if (jsonFile == null || !jsonFile.isFile())
				return;
			JSONValue root = JSONParser.parse(new String(Files.readAllBytes(jsonFile.toPath()), StandardCharsets.UTF_8));
			JSONValue candidates = getMapChild(root, "candidates");
			if (candidates == null || !candidates.isList())
				return;
			String fitKind = getStringChild(root, "fit_kind", getSelectedFitKind());
			ArrayList<Object[]> rows = new ArrayList<>();
			ArrayList<String> distributionNames = new ArrayList<>();
			int position = 1;
			for (JSONValue candidate : candidates.listVal) {
				if (candidate == null || !candidate.isMap())
					continue;
				String distribution = getStringChild(candidate, "distribution", "");
				if (!distribution.isEmpty())
					distributionNames.add(distribution);
				String decision = formatDecision(getStringChild(candidate, "fit_decision", "inconclusiva"));
				String note = firstStringFromList(getMapChild(candidate, "notes"));
				JSONValue parameters = getMapChild(candidate, "parameters");
				String expression = getStringChild(candidate, "display_expression",
						buildDistributionExpression(distribution, parameters));
				rows.add(new Object[] {
						Integer.valueOf(position++),
						distribution,
						fitKind,
						formatNumber(getNumberChild(candidate, "ks_statistic")),
						formatNumber(getNumberChild(candidate, "ks_critical")),
						decision,
						formatAcceptance(getNumberChild(candidate, "score")),
						formatNumber(getNumberChild(candidate, "aic")),
						formatNumber(getNumberChild(candidate, "bic")),
						expression,
						formatParameters(parameters),
						note
				});
			}
			SwingUtilities.invokeLater(() -> {
				distributionTableModel.setRowCount(0);
				for (Object[] row : rows)
					distributionTableModel.addRow(row);
				updateChartDistributionOptions(distributionNames, getStringChild(root, "best_distribution", distributionNames.isEmpty() ? "" : distributionNames.get(0)));
			});
		}
		catch (Exception ex) {
			SwingUtilities.invokeLater(() -> {
				distributionTableModel.setRowCount(0);
				distributionTableModel.addRow(new Object[] {
						"", "Não foi possível ler ranking", "", "", "", ex.getClass().getSimpleName(), "", "", "", "", "", ""
				});
			});
		}
	}

	private static String firstStringFromList(JSONValue list) {
		if (list == null || !list.isList() || list.listVal.isEmpty())
			return "";
		JSONValue first = list.listVal.get(0);
		return first != null && first.isString() ? first.stringVal : "";
	}

	private static String formatDecision(String decision) {
		String normalized = decision == null ? "" : Normalizer.normalize(decision, Normalizer.Form.NFD)
				.replaceAll("\\p{M}", "")
				.toLowerCase(Locale.ROOT)
				.trim();
		if (normalized.contains("nao_rejeitada") || normalized.contains("nao rejeitada"))
			return "não rejeitada";
		if (normalized.contains("rejeitada"))
			return "rejeitada";
		return "inconclusiva";
	}

	private static String formatAcceptance(Double value) {
		if (value == null)
			return "";
		double clamped = Math.max(0.0, Math.min(100.0, value.doubleValue()));
		return String.format(new Locale("pt", "BR"), "%.1f", clamped);
	}

	private static String formatNumber(Double value) {
		if (value == null)
			return "";
		return String.format(Locale.US, "%.6g", value.doubleValue());
	}

	private static String formatExpressionNumber(Double value) {
		if (value == null)
			return "?";
		String text = String.format(Locale.US, "%.6g", value.doubleValue());
		return text.replace('.', ',');
	}

	private static Double getParameterNumber(JSONValue parameters, String key) {
		if (parameters == null || !parameters.isMap())
			return null;
		JSONValue value = getMapChild(parameters, key);
		if (value == null || !value.isNumber())
			return null;
		return Double.valueOf(value.numVal);
	}

	private static int getParameterListSize(JSONValue parameters, String key) {
		JSONValue value = getMapChild(parameters, key);
		if (value == null || !value.isList())
			return 0;
		return value.listVal.size();
	}

	private static String buildDistributionExpression(String distribution, JSONValue parameters) {
		String name = distribution == null ? "" : distribution.toLowerCase(Locale.ROOT);
		if ("normal".equals(name)) {
			return "Normal(μ=" + formatExpressionNumber(getParameterNumber(parameters, "mean"))
					+ ", σ=" + formatExpressionNumber(getParameterNumber(parameters, "standard_deviation")) + ")";
		}
		if ("lognormal".equals(name)) {
			return "Lognormal(μlog=" + formatExpressionNumber(getParameterNumber(parameters, "mean_log"))
					+ ", σlog=" + formatExpressionNumber(getParameterNumber(parameters, "standard_deviation_log")) + ")";
		}
		if ("exponential".equals(name)) {
			return "Exponencial(média=" + formatExpressionNumber(getParameterNumber(parameters, "mean")) + ")";
		}
		if ("uniform".equals(name)) {
			return "Uniforme(min=" + formatExpressionNumber(getParameterNumber(parameters, "minimum"))
					+ ", max=" + formatExpressionNumber(getParameterNumber(parameters, "maximum")) + ")";
		}
		if ("triangular".equals(name)) {
			return "Triangular(min=" + formatExpressionNumber(getParameterNumber(parameters, "minimum"))
					+ ", moda=" + formatExpressionNumber(getParameterNumber(parameters, "mode"))
					+ ", max=" + formatExpressionNumber(getParameterNumber(parameters, "maximum")) + ")";
		}
		if ("poisson".equals(name)) {
			return "Poisson(λ=" + formatExpressionNumber(getParameterNumber(parameters, "mean")) + ")";
		}
		if ("discrete_uniform".equals(name)) {
			return "Uniforme discreta(min=" + formatExpressionNumber(getParameterNumber(parameters, "minimum"))
					+ ", max=" + formatExpressionNumber(getParameterNumber(parameters, "maximum")) + ")";
		}
		if ("empirical_discrete".equals(name)) {
			return "Empírica discreta(" + getParameterListSize(parameters, "values") + " valores)";
		}
		return distribution == null ? "" : distribution;
	}

	private static String formatParameters(JSONValue parameters) {
		if (parameters == null || !parameters.isMap())
			return "";
		StringBuilder sb = new StringBuilder();
		for (Map.Entry<String, JSONValue> entry : parameters.mapVal.entrySet()) {
			if (sb.length() > 0)
				sb.append("; ");
			sb.append(entry.getKey()).append("=");
			JSONValue value = entry.getValue();
			if (value == null)
				sb.append("null");
			else if (value.isNumber())
				sb.append(formatNumber(Double.valueOf(value.numVal)));
			else if (value.isString())
				sb.append(value.stringVal);
			else if (value.isList())
				sb.append("[").append(value.listVal.size()).append(" valores]");
			else
				sb.append("...");
		}
		return sb.toString();
	}

	private void updateChartStatus(String message) {
		SwingUtilities.invokeLater(() -> chartStatusLabel.setText(message));
	}

	private String getSelectedChartDistribution() {
		Object selected = chartDistributionCombo.getSelectedItem();
		String value = selected == null ? "" : selected.toString().trim();
		return value.isEmpty() ? null : value;
	}

	private void selectChartDistribution(String distribution) {
		if (distribution == null || distribution.trim().isEmpty())
			return;
		String clean = distribution.trim();
		SwingUtilities.invokeLater(() -> {
			updatingChartDistributionCombo = true;
			chartDistributionCombo.setSelectedItem(clean);
			updatingChartDistributionCombo = false;
			if (latestJsonReportFile != null)
				updateEmbeddedChartsFromJson(latestJsonReportFile, clean);
		});
	}

	private void updateChartDistributionOptions(List<String> distributions, String preferred) {
		String previous = getSelectedChartDistribution();
		String selected = preferred != null && distributions.contains(preferred) ? preferred : previous;
		if (selected == null || !distributions.contains(selected))
			selected = distributions.isEmpty() ? null : distributions.get(0);
		final String selectedValue = selected;
		SwingUtilities.invokeLater(() -> {
			updatingChartDistributionCombo = true;
			chartDistributionCombo.removeAllItems();
			for (String distribution : distributions)
				chartDistributionCombo.addItem(distribution);
			chartDistributionCombo.setEnabled(!distributions.isEmpty());
			if (selectedValue != null)
				chartDistributionCombo.setSelectedItem(selectedValue);
			updatingChartDistributionCombo = false;
		});
	}

	private static List<double[]> readPointList(JSONValue root, String key, String xKey, String yKey) {
		ArrayList<double[]> values = new ArrayList<>();
		JSONValue list = getMapChild(root, key);
		if (list == null || !list.isList())
			return values;
		for (JSONValue item : list.listVal) {
			if (item == null || !item.isMap())
				continue;
			Double x = getNumberChild(item, xKey);
			Double y = getNumberChild(item, yKey);
			if (x != null && y != null)
				values.add(new double[] { x.doubleValue(), y.doubleValue() });
		}
		return values;
	}

	private static List<double[]> readDiagnosticPointList(JSONValue root, String distribution,
			String listKey, String xKey, String yKey) {
		JSONValue diagnostics = getMapChild(root, "diagnostics_by_distribution");
		if (diagnostics == null || !diagnostics.isMap() || distribution == null)
			return new ArrayList<>();
		JSONValue distributionDiagnostics = diagnostics.mapVal.get(distribution);
		if (distributionDiagnostics == null)
			distributionDiagnostics = diagnostics.mapVal.get(distribution.toLowerCase(Locale.ROOT));
		return readPointList(distributionDiagnostics, listKey, xKey, yKey);
	}

	private static FitCurve readBestFitCurve(JSONValue root) {
		return readFitCurve(firstCandidate(root));
	}

	private static JSONValue firstCandidate(JSONValue root) {
		JSONValue candidates = getMapChild(root, "candidates");
		if (candidates == null || !candidates.isList() || candidates.listVal.isEmpty())
			return null;
		JSONValue first = candidates.listVal.get(0);
		if (first == null || !first.isMap())
			return null;
		return first;
	}

	private static JSONValue findCandidate(JSONValue root, String distribution) {
		if (distribution == null || distribution.trim().isEmpty())
			return null;
		String selected = distribution.trim().toLowerCase(Locale.ROOT);
		JSONValue candidates = getMapChild(root, "candidates");
		if (candidates == null || !candidates.isList())
			return null;
		for (JSONValue candidate : candidates.listVal) {
			if (candidate == null || !candidate.isMap())
				continue;
			String name = getStringChild(candidate, "distribution", "").toLowerCase(Locale.ROOT);
			if (selected.equals(name))
				return candidate;
		}
		return null;
	}

	private static FitCurve readFitCurve(JSONValue candidate) {
		if (candidate == null || !candidate.isMap())
			return null;
		String distribution = getStringChild(candidate, "distribution", "");
		JSONValue parameters = getMapChild(candidate, "parameters");
		if (distribution.isEmpty() || parameters == null || !parameters.isMap())
			return null;
		Map<String, Double> values = new HashMap<>();
		for (Map.Entry<String, JSONValue> entry : parameters.mapVal.entrySet()) {
			if (entry.getValue() != null && entry.getValue().isNumber())
				values.put(entry.getKey(), Double.valueOf(entry.getValue().numVal));
		}
		List<Double> empiricalValues = readNumberListChild(parameters, "values");
		List<Double> empiricalProbabilities = readNumberListChild(parameters, "probabilities");
		return new FitCurve(distribution, values, empiricalValues, empiricalProbabilities);
	}

	private static List<Double> readNumberListChild(JSONValue parent, String key) {
		ArrayList<Double> values = new ArrayList<>();
		JSONValue list = getMapChild(parent, key);
		if (list == null || !list.isList())
			return values;
		for (JSONValue item : list.listVal) {
			if (item != null && item.isNumber())
				values.add(Double.valueOf(item.numVal));
		}
		return values;
	}

	private static JSONValue getMapChild(JSONValue parent, String key) {
		if (parent == null || !parent.isMap())
			return null;
		return parent.mapVal.get(key);
	}

	private static String getStringChild(JSONValue parent, String key, String fallback) {
		JSONValue value = getMapChild(parent, key);
		if (value == null || !value.isString())
			return fallback;
		return value.stringVal;
	}

	private static Double getNumberChild(JSONValue parent, String key) {
		JSONValue value = getMapChild(parent, key);
		if (value == null || !value.isNumber())
			return null;
		return Double.valueOf(value.numVal);
	}

	private void openLatestStatFitCharts() {
		try {
			File anchorFile = new File(".");
			String dataFileText = dataFileField.getText().trim();
			if (!dataFileText.isEmpty())
				anchorFile = new File(dataFileText);

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir gráficos: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			Path outputDir = assistantRoot.resolve("output")
					.resolve("statfit");
			File histogram = latestHistogramFile != null && latestHistogramFile.isFile()
					? latestHistogramFile
					: findLatestFile(outputDir.toFile(), "_histograma.svg");
			File ecdf = latestEcdfFile != null && latestEcdfFile.isFile()
					? latestEcdfFile
					: findLatestFile(outputDir.toFile(), "_cdf_empirica.svg");
			File qq = latestQqFile != null && latestQqFile.isFile()
					? latestQqFile
					: findLatestFile(outputDir.toFile(), "_qq_plot.svg");
			File pp = latestPpFile != null && latestPpFile.isFile()
					? latestPpFile
					: findLatestFile(outputDir.toFile(), "_pp_plot.svg");

			if (histogram == null && ecdf == null && qq == null && pp == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir gráficos: nenhum SVG encontrado ainda. Rode Ajustar distribuição primeiro."
						+ System.lineSeparator());
				updateState("Sem gráficos gerados");
				return;
			}

			if (histogram != null)
				openFile(histogram.toPath(), "Abrir histograma");
			if (ecdf != null)
				openFile(ecdf.toPath(), "Abrir CDF empírica");
			if (qq != null)
				openFile(qq.toPath(), "Abrir gráfico Q-Q");
			if (pp != null)
				openFile(pp.toPath(), "Abrir gráfico P-P");
			updateState("Gráficos abertos");
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao abrir gráficos: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
			updateState("Erro ao abrir gráficos");
		}
	}

	private void openLatestStatFitReport() {
		try {
			File anchorFile = new File(".");
			String dataFileText = dataFileField.getText().trim();
			if (!dataFileText.isEmpty())
				anchorFile = new File(dataFileText);

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir relatório: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			Path outputDir = assistantRoot.resolve("output")
					.resolve("statfit");
			File report = latestMarkdownReportFile != null && latestMarkdownReportFile.isFile()
					? latestMarkdownReportFile
					: findLatestFile(outputDir.toFile(), "_statfit_report.md");

			if (report == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir relatório: nenhum relatório encontrado ainda. Rode Ajustar distribuição primeiro."
						+ System.lineSeparator());
				updateState("Sem relatório gerado");
				return;
			}

			openFile(report.toPath(), "Abrir relatório StatFit");
			updateState("Relatório aberto");
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao abrir relatório: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
			updateState("Erro ao abrir relatório");
		}
	}

	private void copyLatestStatFitSnippet() {
		try {
			File anchorFile = new File(".");
			String dataFileText = dataFileField.getText().trim();
			if (!dataFileText.isEmpty())
				anchorFile = new File(dataFileText);

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Copiar distribuição JaamSim: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			Path outputDir = assistantRoot.resolve("output")
					.resolve("statfit");
			File snippet = latestSnippetFile != null && latestSnippetFile.isFile()
					? latestSnippetFile
					: findLatestFile(outputDir.toFile(), "_jaamsim_distribution.cfg");

			if (snippet == null) {
				appendStatusText(System.lineSeparator()
						+ "Copiar distribuição JaamSim: nenhum arquivo .cfg encontrado ainda. Rode AutoFit primeiro."
						+ System.lineSeparator());
				updateState("Sem distribuição gerada");
				return;
			}

			String snippetText = new String(Files.readAllBytes(snippet.toPath()), StandardCharsets.UTF_8);
			StringSelection selection = new StringSelection(snippetText);
			Toolkit.getDefaultToolkit().getSystemClipboard().setContents(selection, null);
			appendStatusText(System.lineSeparator()
					+ "Copiar distribuição JaamSim: bloco .cfg copiado. Revise parâmetros, unidade e processo real antes de colar no modelo."
					+ System.lineSeparator());
			updateState("Distribuição .cfg copiada");
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao copiar distribuição JaamSim: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
			updateState("Erro ao copiar distribuição");
		}
	}

	private static File findLatestFile(File folder, String suffix) {
		return StatFitRunArtifacts.findLatestFile(folder, suffix);
	}

	private void appendStatusText(final String text) {
		final String cleanText = cleanDisplayText(text);
		SwingUtilities.invokeLater(() -> {
			statusArea.append(cleanText);
			statusArea.setCaretPosition(statusArea.getDocument().getLength());
		});
	}

	private void appendAssistText(final String text) {
		final String cleanText = cleanDisplayText(text);
		SwingUtilities.invokeLater(() -> {
			assistArea.append(cleanText);
			assistArea.setCaretPosition(assistArea.getDocument().getLength());
		});
	}

	private static String cleanDisplayText(String text) {
		if (text == null || text.isEmpty())
			return "";

		String normalized = Normalizer.normalize(text, Normalizer.Form.NFC)
				.replace("Ã¡", "á").replace("Ã ", "à").replace("Ã¢", "â").replace("Ã£", "ã")
				.replace("Ã©", "é").replace("Ãª", "ê")
				.replace("Ã­", "í")
				.replace("Ã³", "ó").replace("Ã´", "ô").replace("Ãµ", "õ")
				.replace("Ãº", "ú").replace("Ã¼", "ü")
				.replace("Ã§", "ç")
				.replace("â€“", "–").replace("â€”", "—")
				.replace("\r\n", "\n")
				.replace('\r', '\n')
				.replace('\t', ' ')
				.replace('\u00A0', ' ')
				.replace('\u2007', ' ')
				.replace('\u202F', ' ')
				.replace("\u00AD", "")
				.replace("\u200B", "")
				.replace("\u200C", "")
				.replace("\u200D", "")
				.replace("\uFEFF", "");

		String[] lines = normalized.split("\n", -1);
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < lines.length; i++) {
			if (i > 0)
				sb.append(System.lineSeparator());
			String line = lines[i].trim().replaceAll(" {2,}", " ");
			sb.append(repairPortugueseAccentSpacing(line));
		}
		return sb.toString();
	}

	private static String repairPortugueseAccentSpacing(String line) {
		if (line == null || line.isEmpty())
			return "";

		String repaired = line;
		repaired = repaired.replaceAll("\u00E7\\s+\u00E3\\s*o", "\u00E7\u00E3o");
		repaired = repaired.replaceAll("\u00C7\\s+\u00C3\\s*O", "\u00C7\u00C3O");
		repaired = repaired.replaceAll("\u00E7\\s+\u00F5\\s*es", "\u00E7\u00F5es");
		repaired = repaired.replaceAll("\u00C7\\s+\u00D5\\s*ES", "\u00C7\u00D5ES");
		repaired = repaired.replaceAll("\u00E3\\s+o\\b", "\u00E3o");
		repaired = repaired.replaceAll("\u00C3\\s+O\\b", "\u00C3O");
		repaired = repaired.replaceAll("\u00F5\\s+es\\b", "\u00F5es");
		repaired = repaired.replaceAll("\u00D5\\s+ES\\b", "\u00D5ES");
		repaired = repaired.replaceAll("(?iu)(^|\\s)\u00FA\\s+teis\\b", "$1\u00FAteis");
		repaired = repairKnownPortugueseWordSpacing(repaired);
		return repaired;
	}

	private static String repairKnownPortugueseWordSpacing(String line) {
		String repaired = line;
		repaired = repaired.replaceAll("(?iu)hor\u00E1\\s+rio\\b", "hor\u00E1rio");
		repaired = repaired.replaceAll("(?iu)m\u00E9\\s+dia\\b", "m\u00E9dia");
		repaired = repaired.replaceAll("(?iu)m\u00E9\\s+dio\\b", "m\u00E9dio");
		repaired = repaired.replaceAll("(?iu)m\u00ED\\s+nimo\\b", "m\u00EDnimo");
		repaired = repaired.replaceAll("(?iu)m\u00E1\\s+ximo\\b", "m\u00E1ximo");
		repaired = repaired.replaceAll("(?iu)par\u00E2\\s+metros\\b", "par\u00E2metros");
		repaired = repaired.replaceAll("(?iu)per\u00ED\\s+odo\\b", "per\u00EDodo");
		repaired = repaired.replaceAll("(?iu)determin\u00ED\\s+stic([ao]s?)\\b", "determin\u00EDstic$1");
		repaired = repaired.replaceAll("(?iu)s\u00E1\\s+bado\\b", "s\u00E1bado");
		repaired = repaired.replaceAll("(?iu)manh\\s+\u00E3\\b", "manh\u00E3");
		return repaired;
	}

	private List<String> buildDataAssistCommand(File dataFile, Path script, Path outputDir) {
		return buildOfflineDataAssistCommand(resolvePythonCommand(), dataFile, script,
				outputDir, columnField.getText().trim());
	}

	/**
	 * Fail closed: preparing a dataset is a LOCAL operation. In particular,
	 * never add --online or a provider order merely because the user clicked
	 * "Preparar dados". A separate explicit opt-in workflow would be needed
	 * for network calls, and none is enabled by this native button.
	 *
	 * Kept independently testable to prevent accidental reintroduction of
	 * online provider invocation in the native StatFit interface.
	 */
	private static List<String> buildOfflineDataAssistCommand(String python, File dataFile,
			Path script, Path outputDir, String column) {
		ArrayList<String> command = new ArrayList<>();
		command.add(python);
		command.add(script.toString());
		command.add(dataFile.getAbsolutePath());
		command.add("--output-dir");
		command.add(outputDir.toString());
		if (column != null && !column.trim().isEmpty()) {
			command.add("--column");
			command.add(column.trim());
		}
		return command;
	}

	private List<String> buildStatFitCommand(File dataFile, Path script, Path outputDir) {
		ArrayList<String> command = new ArrayList<>();
		command.add(resolvePythonCommand());
		command.add(script.toString());
		command.add(dataFile.getAbsolutePath());
		command.add("--output-dir");
		command.add(outputDir.toString());
		command.add("--auto-clean");
		command.add("--fit-kind");
		command.add(getSelectedFitKind());
		command.add("--support");
		command.add(getSelectedSupportMode());

		String column = columnField.getText().trim();
		if (!column.isEmpty()) {
			command.add("--column");
			command.add(column);
		}

		String objectName = objectNameField.getText().trim();
		if (!objectName.isEmpty()) {
			command.add("--jaamsim-object-name");
			command.add(objectName);
		}

		command.add("--unit-type");
		command.add("TimeUnit");
		command.add("--unit");
		command.add("s");
		command.add("--random-seed");
		command.add("11");
		return command;
	}

	private String getSelectedFitKind() {
		return fitKindCombo.getSelectedIndex() == 1 ? "discrete" : "continuous";
	}

	private String getSelectedSupportMode() {
		switch (supportCombo.getSelectedIndex()) {
		case 1:
			return "positive";
		case 2:
			return "bounded";
		case 3:
			return "unbounded";
		default:
			return "auto";
		}
	}

	private static Path findAssistantRoot(File dataFile) {
		// An explicitly configured extension is authoritative. If missing,
		// never silently execute another Python module found near the CFG or
		// in the JVM working directory. This applies equally to GUI and StatFit.
		// The original CMD verifies the native package before setting this
		// environment root. Do not let -Djaamsim.assistant.root supersede it.
		String configuredRoot = AssistantLaunchSettings.preferLauncherEnvironment(
				System.getenv("JAAMSIM_ASSISTANT_ROOT"),
				System.getProperty("jaamsim.assistant.root"));
		if (configuredRoot != null)
			return resolveAssistantRootCandidate(Paths.get(configuredRoot), "statfit_auxiliar.py");

		// Legacy discovery is allowed only when neither source configured a root.
		ArrayList<Path> candidates = new ArrayList<>();
		Path currentDir = Paths.get("").toAbsolutePath();
		candidates.add(currentDir);

		Path cursor = dataFile.toPath().toAbsolutePath().getParent();
		while (cursor != null) {
			candidates.add(cursor);
			cursor = cursor.getParent();
		}

		for (Path candidate : candidates) {
			Path resolved = resolveAssistantRootCandidate(candidate, "statfit_auxiliar.py");
			if (resolved != null)
				return resolved;
		}
		return null;
	}

	private static Path resolveAssistantRootCandidate(Path candidate, String requiredScript) {
		Path normalized = candidate.toAbsolutePath().normalize();
		if (Files.isRegularFile(normalized.resolve("python").resolve(requiredScript)))
			return normalized;

		Path nested = normalized.resolve("extensions").resolve("academic-assistant");
		if (Files.isRegularFile(nested.resolve("python").resolve(requiredScript)))
			return nested;
		return null;
	}

	private static void addConfiguredCandidate(List<Path> candidates, String value) {
		if (value == null || value.trim().isEmpty())
			return;
		candidates.add(Paths.get(value.trim()));
	}

	private static String resolvePythonCommand() {
		// Same trust boundary as the configured assistant root. In a CMD
		// launch, JAAMSIM_PYTHON is the interpreter validated on option 8.
		String configured = AssistantLaunchSettings.preferLauncherEnvironment(
				System.getenv("JAAMSIM_PYTHON"),
				System.getProperty("jaamsim.python"));
		return configured == null ? "python" : configured;
	}

	private static StatFitRunResult executeCommand(List<String> command, Path workingDir, int timeoutSeconds)
			throws IOException, InterruptedException {
		ProcessBuilder builder = new ProcessBuilder(command);
		builder.directory(workingDir.toFile());
		builder.redirectErrorStream(true);
		builder.environment().put("PYTHONIOENCODING", "utf-8");
		builder.environment().put("PYTHONUTF8", "1");

		Process process = builder.start();
		StringBuilder output = new StringBuilder();
		Thread outputThread = new Thread(() -> readProcessOutput(process, output), "JaamSim StatFit Output");
		outputThread.setDaemon(true);
		outputThread.start();

		boolean finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
		if (!finished)
			process.destroyForcibly();

		outputThread.join(3000);
		int exitCode = finished ? process.exitValue() : -1;
		return new StatFitRunResult(finished, exitCode, output.toString());
	}

	private void openFolder(Path folder, String label) throws IOException {
		Files.createDirectories(folder);
		if (!Desktop.isDesktopSupported()) {
			appendStatusText(System.lineSeparator() + label + ": desktop integration is not supported here. Folder: "
					+ folder.toAbsolutePath() + System.lineSeparator());
			return;
		}
		Desktop.getDesktop().open(folder.toFile());
		appendStatusText(System.lineSeparator() + label + ": opened " + folder.toAbsolutePath()
				+ System.lineSeparator());
	}

	private void openFile(Path file, String label) throws IOException {
		if (!Files.isRegularFile(file)) {
			appendStatusText(System.lineSeparator() + label + ": arquivo não encontrado: "
					+ file.toAbsolutePath() + System.lineSeparator());
			return;
		}
		if (!Desktop.isDesktopSupported()) {
			appendStatusText(System.lineSeparator() + label + ": desktop integration is not supported here. File: "
					+ file.toAbsolutePath() + System.lineSeparator());
			return;
		}
		Desktop.getDesktop().open(file.toFile());
		appendStatusText(System.lineSeparator() + label + ": opened " + file.toAbsolutePath()
				+ System.lineSeparator());
	}

	private static void readProcessOutput(Process process, StringBuilder output) {
		try (BufferedReader reader = new BufferedReader(
				new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
			String line;
			while ((line = reader.readLine()) != null) {
				output.append(line).append(System.lineSeparator());
			}
		}
		catch (IOException ex) {
			output.append("Could not read process output: ");
			output.append(ex.getMessage());
			output.append(System.lineSeparator());
		}
	}

	private static String limitOutput(String output, int maxChars) {
		if (output.length() <= maxChars)
			return output;
		return output.substring(0, maxChars)
				+ System.lineSeparator()
				+ "... output truncated in native panel; see markdown/json files in the output folder.";
	}

	private static final class FitCurve {

		private final String distribution;
		private final Map<String, Double> parameters;
		private final List<Double> values;
		private final List<Double> probabilities;

		private FitCurve(String distribution, Map<String, Double> parameters) {
			this(distribution, parameters, new ArrayList<>(), new ArrayList<>());
		}

		private FitCurve(String distribution, Map<String, Double> parameters,
				List<Double> values, List<Double> probabilities) {
			this.distribution = distribution == null ? "" : distribution.toLowerCase(Locale.ROOT);
			this.parameters = parameters == null ? new HashMap<>() : parameters;
			this.values = values == null ? new ArrayList<>() : values;
			this.probabilities = probabilities == null ? new ArrayList<>() : probabilities;
		}

		private double density(double x) {
			if ("normal".equals(distribution)) {
				double mean = value("mean");
				double sd = Math.max(value("standard_deviation"), 1.0e-12);
				double z = (x - mean) / sd;
				return Math.exp(-0.5 * z * z) / (sd * Math.sqrt(2.0 * Math.PI));
			}
			if ("lognormal".equals(distribution)) {
				if (x <= 0.0)
					return 0.0;
				double meanLog = value("mean_log");
				double sdLog = Math.max(value("standard_deviation_log"), 1.0e-12);
				double z = (Math.log(x) - meanLog) / sdLog;
				return Math.exp(-0.5 * z * z) / (x * sdLog * Math.sqrt(2.0 * Math.PI));
			}
			if ("exponential".equals(distribution)) {
				if (x < 0.0)
					return 0.0;
				double rate = value("rate");
				if (rate <= 0.0) {
					double mean = value("mean");
					rate = mean > 0.0 ? 1.0 / mean : 0.0;
				}
				return rate > 0.0 ? rate * Math.exp(-rate * x) : 0.0;
			}
			if ("uniform".equals(distribution)) {
				double minimum = value("minimum");
				double maximum = value("maximum");
				return x >= minimum && x <= maximum && maximum > minimum ? 1.0 / (maximum - minimum) : 0.0;
			}
			if ("triangular".equals(distribution)) {
				double minimum = value("minimum");
				double mode = value("mode");
				double maximum = value("maximum");
				if (x < minimum || x > maximum || maximum <= minimum)
					return 0.0;
				if (x <= mode && mode > minimum)
					return 2.0 * (x - minimum) / ((maximum - minimum) * (mode - minimum));
				if (maximum > mode)
					return 2.0 * (maximum - x) / ((maximum - minimum) * (maximum - mode));
			}
			if ("poisson".equals(distribution)) {
				double mean = value("mean");
				int k = (int) Math.round(x);
				if (mean <= 0.0 || k < 0 || Math.abs(x - k) > 0.5)
					return 0.0;
				double logProbability = k * Math.log(mean) - mean - logFactorial(k);
				return Math.exp(logProbability);
			}
			if ("discrete_uniform".equals(distribution)) {
				double minimum = value("minimum");
				double maximum = value("maximum");
				int k = (int) Math.round(x);
				if (k < minimum || k > maximum || Math.abs(x - k) > 0.5 || maximum < minimum)
					return 0.0;
				return 1.0 / (maximum - minimum + 1.0);
			}
			if ("empirical_discrete".equals(distribution)) {
				int k = (int) Math.round(x);
				if (Math.abs(x - k) > 0.5)
					return 0.0;
				for (int i = 0; i < values.size() && i < probabilities.size(); i++) {
					if ((int) Math.round(values.get(i).doubleValue()) == k)
						return Math.max(0.0, probabilities.get(i).doubleValue());
				}
			}
			return 0.0;
		}

		private static double logFactorial(int value) {
			double total = 0.0;
			for (int i = 2; i <= value; i++)
				total += Math.log(i);
			return total;
		}

		private double value(String key) {
			Double value = parameters.get(key);
			return value == null ? 0.0 : value.doubleValue();
		}
	}

	private static final class StatFitChartView extends JPanel {

		private enum Mode {
			HISTOGRAM,
			POINTS,
			POINTS_WITH_DIAGONAL
		}

		private final String title;
		private final Mode mode;
		private List<double[]> data = new ArrayList<>();
		private FitCurve curve;

		private StatFitChartView(String title, Mode mode) {
			this.title = title;
			this.mode = mode;
			setBackground(PANEL_COLOR);
			setBorder(BorderFactory.createLineBorder(BORDER_COLOR));
			setPreferredSize(new Dimension(280, 200));
		}

		private void setData(List<double[]> data) {
			this.data = data == null ? new ArrayList<>() : new ArrayList<>(data);
			repaint();
		}

		private void setCurve(FitCurve curve) {
			this.curve = curve;
			repaint();
		}

		@Override
		protected void paintComponent(Graphics g) {
			super.paintComponent(g);
			Graphics2D g2 = (Graphics2D) g.create();
			try {
				g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
				int width = getWidth();
				int height = getHeight();
				int left = 42;
				int right = 16;
				int top = 32;
				int bottom = 34;
				int plotWidth = Math.max(20, width - left - right);
				int plotHeight = Math.max(20, height - top - bottom);

				g2.setColor(new Color(24, 45, 66));
				g2.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 13));
				g2.drawString(title, 12, 20);

				g2.setColor(new Color(110, 124, 138));
				g2.drawLine(left, top, left, top + plotHeight);
				g2.drawLine(left, top + plotHeight, left + plotWidth, top + plotHeight);

				if (data.isEmpty()) {
					g2.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 12));
					g2.drawString("Sem dados ainda", left + 12, top + 32);
					return;
				}

				if (mode == Mode.HISTOGRAM) {
					drawHistogram(g2, left, top, plotWidth, plotHeight);
				}
				else {
					drawPointChart(g2, left, top, plotWidth, plotHeight);
				}
			}
			finally {
				g2.dispose();
			}
		}

		private void drawHistogram(Graphics2D g2, int left, int top, int plotWidth, int plotHeight) {
			double maxCount = 1.0;
			for (double[] point : data)
				maxCount = Math.max(maxCount, point[1]);

			int gap = 4;
			int barWidth = Math.max(4, (plotWidth - gap * (data.size() - 1)) / Math.max(1, data.size()));
			g2.setColor(ACCENT_COLOR);
			for (int i = 0; i < data.size(); i++) {
				double count = data.get(i)[1];
				int barHeight = (int) Math.round((count / maxCount) * (plotHeight - 8));
				int x = left + i * (barWidth + gap);
				int y = top + plotHeight - barHeight;
				g2.fillRect(x, y, barWidth, barHeight);
			}
			if (curve != null)
				drawFitCurve(g2, left, top, plotWidth, plotHeight);
			g2.setColor(new Color(80, 90, 100));
			g2.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 11));
			g2.drawString("freq.", 8, top + 12);
		}

		private void drawFitCurve(Graphics2D g2, int left, int top, int plotWidth, int plotHeight) {
			if (data.size() < 2)
				return;
			double minX = Double.POSITIVE_INFINITY;
			double maxX = Double.NEGATIVE_INFINITY;
			for (double[] point : data) {
				minX = Math.min(minX, point[0]);
				maxX = Math.max(maxX, point[0]);
			}
			if (!Double.isFinite(minX) || !Double.isFinite(maxX) || Math.abs(maxX - minX) < 1.0e-12)
				return;

			int samples = 80;
			double maxDensity = 0.0;
			double[] densities = new double[samples];
			for (int i = 0; i < samples; i++) {
				double x = minX + (maxX - minX) * i / (samples - 1);
				double density = Math.max(0.0, curve.density(x));
				densities[i] = density;
				maxDensity = Math.max(maxDensity, density);
			}
			if (maxDensity <= 0.0)
				return;

			g2.setColor(new Color(205, 65, 65));
			g2.setStroke(new BasicStroke(1.8f));
			int previousX = left;
			int previousY = top + plotHeight;
			for (int i = 0; i < samples; i++) {
				int x = left + (int) Math.round((double) i / (samples - 1) * plotWidth);
				int y = top + plotHeight - (int) Math.round((densities[i] / maxDensity) * (plotHeight - 10));
				if (i > 0)
					g2.drawLine(previousX, previousY, x, y);
				previousX = x;
				previousY = y;
			}
			g2.setStroke(new BasicStroke(1.0f));
		}

		private void drawPointChart(Graphics2D g2, int left, int top, int plotWidth, int plotHeight) {
			double minX = Double.POSITIVE_INFINITY;
			double maxX = Double.NEGATIVE_INFINITY;
			double minY = Double.POSITIVE_INFINITY;
			double maxY = Double.NEGATIVE_INFINITY;
			for (double[] point : data) {
				minX = Math.min(minX, point[0]);
				maxX = Math.max(maxX, point[0]);
				minY = Math.min(minY, point[1]);
				maxY = Math.max(maxY, point[1]);
			}
			if (mode == Mode.POINTS_WITH_DIAGONAL) {
				double min = Math.min(minX, minY);
				double max = Math.max(maxX, maxY);
				minX = min;
				minY = min;
				maxX = max;
				maxY = max;
			}
			if (Math.abs(maxX - minX) < 1.0e-12)
				maxX = minX + 1.0;
			if (Math.abs(maxY - minY) < 1.0e-12)
				maxY = minY + 1.0;

			if (mode == Mode.POINTS_WITH_DIAGONAL) {
				g2.setColor(new Color(205, 65, 65));
				g2.setStroke(new BasicStroke(1.4f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND,
						1.0f, new float[] { 5.0f, 5.0f }, 0.0f));
				g2.drawLine(left, top + plotHeight, left + plotWidth, top);
				g2.setStroke(new BasicStroke(1.0f));
			}

			g2.setColor(ACCENT_COLOR);
			for (double[] point : data) {
				int x = left + (int) Math.round(((point[0] - minX) / (maxX - minX)) * plotWidth);
				int y = top + plotHeight - (int) Math.round(((point[1] - minY) / (maxY - minY)) * plotHeight);
				g2.fillOval(x - 3, y - 3, 6, 6);
			}
		}
	}

	private static final class StatFitRunResult {

		private final boolean finished;
		private final int exitCode;
		private final String output;

		private StatFitRunResult(boolean finished, int exitCode, String output) {
			this.finished = finished;
			this.exitCode = exitCode;
			this.output = output;
		}
	}
}
