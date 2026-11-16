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
 * Academic prototype extension: native AI assistant shell.
 */
package com.jaamsim.ui;

import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Desktop;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.GridBagConstraints;
import java.awt.GridBagLayout;
import java.awt.GridLayout;
import java.awt.Insets;
import java.awt.event.ActionEvent;
import java.awt.event.MouseWheelListener;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.io.ByteArrayOutputStream;
import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.FileTime;
import java.text.Normalizer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

import javax.swing.Box;
import javax.swing.AbstractAction;
import javax.swing.Action;
import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JFileChooser;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollBar;
import javax.swing.JScrollPane;
import javax.swing.JSpinner;
import javax.swing.JTabbedPane;
import javax.swing.JTextArea;
import javax.swing.JTextPane;
import javax.swing.KeyStroke;
import javax.swing.SpinnerNumberModel;
import javax.swing.SwingUtilities;
import javax.swing.Timer;
import javax.swing.text.DefaultEditorKit;
import javax.swing.text.BadLocationException;
import javax.swing.text.SimpleAttributeSet;
import javax.swing.text.StyleConstants;
import javax.swing.text.StyledDocument;
import javax.swing.filechooser.FileNameExtensionFilter;

import com.jaamsim.basicsim.Entity;
import com.jaamsim.basicsim.JaamSimModel;
import com.jaamsim.basicsim.ObjectType;
import com.jaamsim.JSON.JSONParser;
import com.jaamsim.JSON.JSONValue;
import com.jaamsim.JSON.JSONWriter;

/**
 * Native shell for the JaamSim academic simulation assistant.
 *
 * This first integration step is intentionally read-only. It proves that a
 * custom JaamSim build can expose an assistant window from the Tools menu
 * without modifying the model topology.
 */
public class AIAssistantBox extends FrameBox {

	private static final int RCL_TIMEOUT_SECONDS = 60;
	private static final int MAX_PROCESS_OUTPUT_CHARS = 8000;
	private static final int CHAT_MAX_TOKENS = 1200;
	private static final int AUTOSAVE_CHECK_MILLIS = 5000;
	private static final long MAX_ATTACHMENT_BYTES = 25L * 1024L * 1024L;
	private static final String COMPANION_EXTENSION = ".jaamsim-ai.zip";
	private static final Color SURFACE_COLOR = new Color(245, 247, 250);
	private static final Color PANEL_COLOR = new Color(255, 255, 255);
	private static final Color BORDER_COLOR = new Color(205, 211, 218);
	private static final Color ACCENT_COLOR = new Color(42, 101, 176);
	private static final Color SOFT_ACCENT_COLOR = new Color(232, 241, 252);
	private static final Color WARNING_COLOR = new Color(255, 249, 227);

	private static AIAssistantBox myInstance;

	private final JTextPane statusArea;
	private final JTextArea ideaArea;
	private final JScrollPane chatScrollPane;
	private final JCheckBox notificationsCheckBox;
	private final JCheckBox proactiveCheckBox;
	private final JCheckBox onlineAiCheckBox;
	private final JCheckBox autoCorrectionCheckBox;
	private final JCheckBox enterToSendCheckBox;
	private final JCheckBox smoothScrollCheckBox;
	private final JCheckBox autosaveCheckBox;
	private final JSpinner cooldownSpinner;
	private final JSpinner autosaveMinutesSpinner;
	private final JLabel companionStatusLabel;
	private Timer chatScrollTimer;
	private Timer companionAutosaveTimer;
	private int smoothWheelTarget = -1;
	private final ArrayList<String> pendingBriefingQuestions;
	private final ArrayList<String> briefingAnswers;
	private final ArrayList<String> guidedBriefingAnswers;
	private final ArrayList<ConversationTurn> conversationTurns;
	private final ArrayList<AttachmentRecord> companionAttachments;
	private final StringBuilder companionBriefingAnswersMarkdown;
	private Path activeBriefingOutputDir;
	private String activeBriefingCaseId;
	private Path activeChatHistoryFile;
	private String activeChatCaseId;
	private Path transientSessionDir;
	private Path activeCompanionZip;
	private File activeCompanionModelFile;
	private String companionBriefingJson;
	private String companionBriefingMarkdown;
	private String companionHistoryMarkdown;
	private String companionPrdMarkdown;
	private String companionEpicsMarkdown;
	private boolean companionDirty;
	private String guidedBriefingSeed;
	private boolean guidedBriefingActive;
	private boolean welcomeShown;
	private boolean restoringConversation;
	private FileTime lastBackedUpConfigTime;
	private long lastAutosaveMillis;
	private long lastNotificationMillis;

	private static final String[] GUIDED_BRIEFING_QUESTIONS = {
			"Qual processo você quer representar na simulação?",
			"O que entra no sistema? Pode ser pessoa, pedido, matéria-prima, chamada, veículo ou outro fluxo.",
			"Quais são as principais etapas ou recursos que processam essa entidade?",
			"O que sai do sistema e quando você considera que o processo terminou?",
			"Qual decisão você quer apoiar com essa simulação? Por exemplo: capacidade, gargalo, fila, estoque, tempo ou custo."
	};

	private AIAssistantBox() {
		super("Assistente de Simulação IA");
		setType(Type.NORMAL);
		setAutoRequestFocus(true);
		setDefaultCloseOperation(FrameBox.DO_NOTHING_ON_CLOSE);
		addWindowListener(new WindowAdapter() {
			@Override
			public void windowClosing(WindowEvent event) {
				hideAssistantWindow();
			}
		});
		setPreferredSize(new Dimension(840, 680));
		pendingBriefingQuestions = new ArrayList<>();
		briefingAnswers = new ArrayList<>();
		guidedBriefingAnswers = new ArrayList<>();
		conversationTurns = new ArrayList<>();
		companionAttachments = new ArrayList<>();
		companionBriefingAnswersMarkdown = new StringBuilder();
		transientSessionDir = createTransientSessionDir();

		statusArea = new JTextPane();
		statusArea.setEditable(false);
		statusArea.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
		statusArea.setBackground(PANEL_COLOR);
		statusArea.setBorder(BorderFactory.createEmptyBorder(10, 12, 10, 12));

		ideaArea = new JTextArea();
		ideaArea.setRows(4);
		ideaArea.setLineWrap(true);
		ideaArea.setWrapStyleWord(true);
		ideaArea.setTabSize(2);
		ideaArea.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 13));
		ideaArea.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

		JButton sendButton = createActionButton("Enviar",
				"Envia sua mensagem ao assistente. Ele decide se deve orientar, revisar ou gerar briefing.");
		sendButton.setPreferredSize(new Dimension(92, 54));
		sendButton.addActionListener(e -> handleChatSubmit());
		JButton attachButton = createActionButton("Anexar",
				"Registra imagens, fluxos ou arquivos de apoio no pacote companheiro da simulação.");
		attachButton.setPreferredSize(new Dimension(92, 28));
		attachButton.addActionListener(e -> handleAttachFiles());
		JPanel inputActions = new JPanel(new GridLayout(2, 1, 4, 4));
		inputActions.setOpaque(false);
		inputActions.add(attachButton);
		inputActions.add(sendButton);

		JPanel inputPanel = new JPanel(new BorderLayout(6, 4));
		inputPanel.setBorder(BorderFactory.createTitledBorder("Mensagem"));
		inputPanel.setBackground(PANEL_COLOR);
		inputPanel.add(new JScrollPane(ideaArea), BorderLayout.CENTER);
		inputPanel.add(inputActions, BorderLayout.EAST);

		JPanel chatPanel = new JPanel(new BorderLayout(6, 6));
		chatPanel.setBackground(SURFACE_COLOR);
		chatPanel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
		JPanel chatTopPanel = new JPanel(new BorderLayout(6, 6));
		chatTopPanel.setOpaque(false);
		chatTopPanel.add(buildAssistantHeaderPanel(), BorderLayout.NORTH);
		chatTopPanel.add(buildQuickActionPanel(), BorderLayout.SOUTH);
		chatPanel.add(chatTopPanel, BorderLayout.NORTH);
		chatScrollPane = new JScrollPane(statusArea);
		chatScrollPane.setBorder(BorderFactory.createLineBorder(BORDER_COLOR));
		chatScrollPane.getVerticalScrollBar().setUnitIncrement(18);
		chatScrollPane.getVerticalScrollBar().setBlockIncrement(120);
		configureSmoothWheelScroll();
		chatPanel.add(chatScrollPane, BorderLayout.CENTER);
		chatPanel.add(inputPanel, BorderLayout.SOUTH);

		notificationsCheckBox = new JCheckBox("Mostrar notificações assistivas", true);
		proactiveCheckBox = new JCheckBox("Avisar quando os algoritmos locais notarem risco", true);
		onlineAiCheckBox = new JCheckBox("Usar IA online quando disponível", true);
		autoCorrectionCheckBox = new JCheckBox("Autocorreção experimental de fórmulas/valores simples", false);
		enterToSendCheckBox = new JCheckBox("Enter envia mensagem (Shift+Enter quebra linha)", true);
		smoothScrollCheckBox = new JCheckBox("Rolagem suave no chat", true);
		autosaveCheckBox = new JCheckBox("Autosave seguro do assistente e backup do .cfg", true);
		cooldownSpinner = new JSpinner(new SpinnerNumberModel(8, 3, 120, 1));
		autosaveMinutesSpinner = new JSpinner(new SpinnerNumberModel(3, 1, 10, 1));
		companionStatusLabel = new JLabel("Rascunho em memória");
		configureMessageShortcuts();

		JPanel configPanel = buildConfigurationPanel();

		JTabbedPane tabs = new JTabbedPane();
		tabs.addTab("Conversa", chatPanel);
		tabs.addTab("Configurações", configPanel);
		getContentPane().setBackground(SURFACE_COLOR);
		getContentPane().add(tabs, BorderLayout.CENTER);

		refreshCompanionBinding(false);
		if (conversationTurns.isEmpty())
			refreshStatus();
		startCompanionAutosaveTimer();
		pack();
	}

	public synchronized static AIAssistantBox getInstance() {
		if (myInstance == null) {
			myInstance = new AIAssistantBox();
			return myInstance;
		}

		return myInstance;
	}

	private synchronized static void killInstance() {
		myInstance = null;
	}

	private void hideAssistantWindow() {
		refreshCompanionBinding(false);
		persistCompanionIfSaved(false, "hide");
		setVisible(false);
	}

	@Override
	public void dispose() {
		if (!confirmDiscardTransientCompanion())
			return;
		persistCompanionIfSaved(false, "close");
		if (companionAutosaveTimer != null)
			companionAutosaveTimer.stop();
		killInstance();
		super.dispose();
	}

	private void refreshStatus() {
		StringBuilder sb = new StringBuilder();
		if (!welcomeShown) {
			sb.append("Assistente: Oi! Sou seu assistente de simulação no JaamSim.").append(System.lineSeparator());
			sb.append("Assistente: Me conte o processo que você quer modelar, ou peça para revisar o modelo atual. Eu vou fazendo perguntas uma por vez.").append(System.lineSeparator());
			sb.append("Assistente: Eu acompanho o contexto do modelo aberto e mantenho a conversa focada na construção da simulação.").append(System.lineSeparator());
			sb.append(System.lineSeparator());
			welcomeShown = true;
		}

		setOrAppendConversation(sb.toString());
	}

	private static JTextArea createGuideArea(String text) {
		JTextArea area = new JTextArea(cleanDisplayText(text));
		area.setEditable(false);
		area.setLineWrap(true);
		area.setWrapStyleWord(true);
		area.setTabSize(2);
		area.setOpaque(false);
		area.setBorder(BorderFactory.createEmptyBorder(6, 8, 4, 8));
		area.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 12));
		return area;
	}

	private static JButton createActionButton(String text, String tooltip) {
		JButton button = new JButton(text);
		button.setFocusPainted(false);
		button.setToolTipText(tooltip);
		return button;
	}

	private JPanel buildAssistantHeaderPanel() {
		JPanel panel = new JPanel(new BorderLayout(8, 4));
		panel.setBackground(PANEL_COLOR);
		panel.setBorder(BorderFactory.createCompoundBorder(
				BorderFactory.createLineBorder(BORDER_COLOR),
				BorderFactory.createEmptyBorder(10, 12, 10, 12)));

		JLabel title = new JLabel("Copiloto de simulação");
		title.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 15));
		title.setForeground(ACCENT_COLOR);
		panel.add(title, BorderLayout.NORTH);

		JTextArea subtitle = createGuideArea(
				"Converse normalmente. Eu ajudo a estruturar a ideia, revisar o modelo, explicar alertas e preparar dados para distribuições.");
		subtitle.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 0));
		panel.add(subtitle, BorderLayout.CENTER);

		JPanel badges = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
		badges.setOpaque(false);
		badges.add(createBadge("LLM online quando habilitada"));
		badges.add(createBadge("Algoritmos locais para checagens"));
		badges.add(createBadge("Operador decide alterações"));
		panel.add(badges, BorderLayout.SOUTH);
		return panel;
	}

	private JPanel buildQuickActionPanel() {
		JPanel panel = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
		panel.setOpaque(false);
		panel.add(createPromptButton("Dicas", "me dê dicas para continuar"));
		panel.add(createPromptButton("Revisar modelo", "revise meu modelo"));
		panel.add(createPromptButton("Histórico RCL", "mostrar histórico de revisões"));
		panel.add(createPromptButton("Criar PRD", "quero construir uma simulação do zero"));
		panel.add(createPromptButton("Explicar alerta", "explique este alerta"));
		panel.add(createPromptButton("Quando usar StatFit?", "quando uso StatFit?"));
		JButton clearButton = createActionButton("Limpar conversa", "Limpa a conversa desta janela.");
		clearButton.addActionListener(e -> clearConversation());
		panel.add(Box.createHorizontalStrut(8));
		panel.add(clearButton);
		return panel;
	}

	private static JLabel createBadge(String text) {
		JLabel label = new JLabel(text);
		label.setOpaque(true);
		label.setBackground(SOFT_ACCENT_COLOR);
		label.setForeground(new Color(35, 75, 125));
		label.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 11));
		label.setBorder(BorderFactory.createEmptyBorder(3, 7, 3, 7));
		return label;
	}

	private JButton createPromptButton(String label, String prompt) {
		JButton button = createActionButton(label, "Preenche e envia: " + prompt);
		button.addActionListener(e -> {
			ideaArea.setText(prompt);
			handleChatSubmit();
		});
		return button;
	}

	private void clearConversation() {
		setStatusText("");
		conversationTurns.clear();
		activeChatHistoryFile = null;
		markCompanionDirty();
		welcomeShown = false;
		refreshStatus();
	}

	private void handleAttachFiles() {
		JFileChooser chooser = new JFileChooser();
		chooser.setMultiSelectionEnabled(true);
		chooser.setDialogTitle("Anexar arquivo ao assistente");
		chooser.setFileFilter(new FileNameExtensionFilter(
				"Imagens, fluxos e dados",
				"png", "jpg", "jpeg", "gif", "bmp", "svg", "pdf", "bpmn", "xml", "vsdx", "csv", "txt", "xlsx"));
		int result = chooser.showOpenDialog(this);
		if (result != JFileChooser.APPROVE_OPTION)
			return;

		File[] files = chooser.getSelectedFiles();
		if (files == null || files.length == 0)
			return;

		ArrayList<AttachmentRecord> added = new ArrayList<>();
		ArrayList<String> rejected = new ArrayList<>();
		for (File file : files) {
			try {
				AttachmentRecord record = registerAttachment(file);
				added.add(record);
			}
			catch (IOException ex) {
				rejected.add(file.getName() + " (" + ex.getMessage() + ")");
			}
		}

		StringBuilder sb = new StringBuilder();
		if (!added.isEmpty()) {
			sb.append("Registrei ").append(added.size()).append(" anexo(s) no contexto da simulação.");
			sb.append(System.lineSeparator());
			for (AttachmentRecord record : added) {
				sb.append("- ").append(record.originalName)
						.append(" [").append(record.kind).append("]")
						.append(System.lineSeparator());
			}
			sb.append("Eles serão salvos no arquivo companheiro quando o modelo estiver salvo.");
			sb.append(System.lineSeparator());
			sb.append("Leitura visual automática desses anexos fica preparada para uma próxima etapa; por enquanto eu uso como contexto/auditoria.");
		}
		if (!rejected.isEmpty()) {
			if (sb.length() > 0)
				sb.append(System.lineSeparator());
			sb.append("Não consegui anexar:").append(System.lineSeparator());
			for (String item : rejected)
				sb.append("- ").append(item).append(System.lineSeparator());
		}
		appendChatMessage("Assistente", sb.toString());
	}

	private JPanel buildConfigurationPanel() {
		JPanel panel = new JPanel(new GridBagLayout());
		panel.setBackground(SURFACE_COLOR);
		panel.setBorder(BorderFactory.createEmptyBorder(12, 12, 12, 12));
		GridBagConstraints gbc = new GridBagConstraints();
		gbc.gridx = 0;
		gbc.gridy = 0;
		gbc.anchor = GridBagConstraints.WEST;
		gbc.insets = new Insets(4, 4, 4, 4);
		gbc.fill = GridBagConstraints.HORIZONTAL;
		gbc.weightx = 1.0;

		JLabel header = new JLabel("Comportamento do assistente");
		header.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 14));
		header.setForeground(ACCENT_COLOR);
		panel.add(header, gbc);
		gbc.gridy++;
		panel.add(notificationsCheckBox, gbc);
		gbc.gridy++;
		panel.add(proactiveCheckBox, gbc);
		gbc.gridy++;
		panel.add(onlineAiCheckBox, gbc);
		gbc.gridy++;
		panel.add(autoCorrectionCheckBox, gbc);
		gbc.gridy++;
		panel.add(enterToSendCheckBox, gbc);
		gbc.gridy++;
		panel.add(smoothScrollCheckBox, gbc);
		gbc.gridy++;
		panel.add(autosaveCheckBox, gbc);
		gbc.gridy++;

		JPanel cooldownPanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
		cooldownPanel.add(new JLabel("Cooldown das notificações (segundos):"));
		cooldownPanel.add(cooldownSpinner);
		panel.add(cooldownPanel, gbc);
		gbc.gridy++;

		JPanel autosavePanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
		autosavePanel.add(new JLabel("Autosave seguro (minutos):"));
		autosavePanel.add(autosaveMinutesSpinner);
		panel.add(autosavePanel, gbc);
		gbc.gridy++;

		companionStatusLabel.setOpaque(true);
		companionStatusLabel.setBackground(SOFT_ACCENT_COLOR);
		companionStatusLabel.setBorder(BorderFactory.createEmptyBorder(6, 8, 6, 8));
		panel.add(companionStatusLabel, gbc);
		gbc.gridy++;

		JTextArea guardrail = createGuideArea(
				"Autocorreção experimental fica limitada a fórmulas, valores simples e ajustes reversíveis. "
						+ "Topologia, criação de objetos e conexões continuam sob controle do operador.");
		guardrail.setBorder(BorderFactory.createTitledBorder("Guardrails"));
		guardrail.setOpaque(true);
		guardrail.setBackground(WARNING_COLOR);
		panel.add(guardrail, gbc);
		gbc.gridy++;
		gbc.weighty = 1.0;
		panel.add(new JPanel(), gbc);
		return panel;
	}

	private void configureMessageShortcuts() {
		ideaArea.getInputMap().put(KeyStroke.getKeyStroke("ENTER"), "submit-or-insert-break");
		ideaArea.getActionMap().put("submit-or-insert-break", new AbstractAction() {
			@Override
			public void actionPerformed(ActionEvent event) {
				if (enterToSendCheckBox.isSelected()) {
					handleChatSubmit();
					return;
				}
				insertLineBreak(event);
			}
		});
		ideaArea.getInputMap().put(KeyStroke.getKeyStroke("shift ENTER"), DefaultEditorKit.insertBreakAction);
	}

	private void insertLineBreak(ActionEvent event) {
		Action insertBreak = ideaArea.getActionMap().get(DefaultEditorKit.insertBreakAction);
		if (insertBreak != null) {
			insertBreak.actionPerformed(event);
			return;
		}
		ideaArea.append(System.lineSeparator());
	}

	private Path createTransientSessionDir() {
		try {
			return Files.createTempDirectory("jaamsim-ai-session-");
		}
		catch (IOException ex) {
			Path fallback = Paths.get(System.getProperty("java.io.tmpdir"), "jaamsim-ai-session-" + System.currentTimeMillis());
			try {
				Files.createDirectories(fallback);
			}
			catch (IOException ignored) {
				// The helper calls will report the failure if this folder cannot be used.
			}
			return fallback;
		}
	}

	private Path getTransientOutputDir(String name) throws IOException {
		if (transientSessionDir == null)
			transientSessionDir = createTransientSessionDir();
		Path dir = transientSessionDir.resolve(name);
		Files.createDirectories(dir);
		return dir;
	}

	private Path getTransientAttachmentDir() throws IOException {
		return getTransientOutputDir("attachments");
	}

	private AttachmentRecord registerAttachment(File file) throws IOException {
		if (file == null || !file.isFile())
			throw new IOException("arquivo não encontrado");
		long size = file.length();
		if (size > MAX_ATTACHMENT_BYTES)
			throw new IOException("maior que 25 MB");

		String originalName = file.getName();
		String storedName = System.currentTimeMillis() + "_" + sanitizeFileName(originalName);
		Path target = getTransientAttachmentDir().resolve(storedName);
		Files.copy(file.toPath(), target, StandardCopyOption.REPLACE_EXISTING);
		AttachmentRecord record = new AttachmentRecord(originalName, storedName, target.toString(),
				inferAttachmentKind(originalName), size, OffsetDateTime.now().toString());
		companionAttachments.add(record);
		markCompanionDirty();
		persistCompanionIfSaved(false, "attachment");
		return record;
	}

	private void restoreAttachmentFromZip(ZipInputStream zip, String entryName) throws IOException {
		String name = entryName.substring(entryName.lastIndexOf('/') + 1);
		String storedName = sanitizeFileName(name);
		Path target = getTransientAttachmentDir().resolve(storedName);
		Files.copy(zip, target, StandardCopyOption.REPLACE_EXISTING);
		long size = Files.size(target);
		if (!hasAttachmentStoredName(storedName)) {
			companionAttachments.add(new AttachmentRecord(storedName, storedName, target.toString(),
					inferAttachmentKind(storedName), size, OffsetDateTime.now().toString()));
		}
	}

	private boolean hasAttachmentStoredName(String storedName) {
		for (AttachmentRecord record : companionAttachments) {
			if (record.storedName.equals(storedName))
				return true;
		}
		return false;
	}

	private void startCompanionAutosaveTimer() {
		companionAutosaveTimer = new Timer(AUTOSAVE_CHECK_MILLIS, event -> runCompanionAutosaveTick());
		companionAutosaveTimer.setRepeats(true);
		companionAutosaveTimer.start();
	}

	private void runCompanionAutosaveTick() {
		refreshCompanionBinding(false);
		if (!autosaveCheckBox.isSelected() || activeCompanionZip == null) {
			updateCompanionStatusLabel();
			return;
		}

		long now = System.currentTimeMillis();
		long intervalMs = ((Integer) autosaveMinutesSpinner.getValue()).intValue() * 60_000L;
		if (now - lastAutosaveMillis < intervalMs)
			return;

		persistCompanionIfSaved(true, "autosave");
		lastAutosaveMillis = now;
		updateCompanionStatusLabel();
	}

	private void refreshCompanionBinding(boolean persistWhenSaved) {
		File cfgFile = getCurrentConfigFile();
		if (cfgFile == null) {
			updateCompanionStatusLabel();
			return;
		}

		Path companion = buildCompanionZipPath(cfgFile);
		if (sameFile(cfgFile, activeCompanionModelFile) && companion.equals(activeCompanionZip)) {
			if (persistWhenSaved)
				persistCompanionIfSaved(false, "refresh");
			updateCompanionStatusLabel();
			return;
		}

		activeCompanionModelFile = cfgFile;
		activeCompanionZip = companion;
		activeChatCaseId = buildModelId(cfgFile);
		activeChatHistoryFile = null;
		lastBackedUpConfigTime = null;

		if (conversationTurns.isEmpty() && Files.isRegularFile(companion)) {
			loadCompanionZip(companion);
			companionDirty = false;
		}
		else {
			companionDirty = true;
			persistCompanionIfSaved(false, "bind");
		}
		updateCompanionStatusLabel();
	}

	private static File getCurrentConfigFile() {
		JaamSimModel simModel = GUIFrame.getJaamSimModel();
		if (simModel == null)
			return null;
		return simModel.getConfigFile();
	}

	private static boolean sameFile(File left, File right) {
		if (left == null || right == null)
			return false;
		return left.toPath().toAbsolutePath().normalize().equals(right.toPath().toAbsolutePath().normalize());
	}

	private static Path buildCompanionZipPath(File cfgFile) {
		Path cfgPath = cfgFile.toPath().toAbsolutePath().normalize();
		String name = cfgPath.getFileName().toString();
		int dot = name.lastIndexOf('.');
		if (dot > 0)
			name = name.substring(0, dot);
		return cfgPath.resolveSibling(name + COMPANION_EXTENSION);
	}

	private void updateCompanionStatusLabel() {
		if (companionStatusLabel == null)
			return;

		String text;
		if (activeCompanionZip != null) {
			text = autosaveCheckBox != null && autosaveCheckBox.isSelected()
					? "Autosave ativo: " + activeCompanionZip.getFileName()
					: "Arquivo companheiro: " + activeCompanionZip.getFileName();
		}
		else if (companionDirty || !conversationTurns.isEmpty()) {
			text = "Rascunho em memória: salve o modelo para preservar conversa, PRD e épicos/stories.";
		}
		else {
			text = "Salvar modelo para ativar arquivo companheiro e autosave.";
		}

		final String clean = cleanDisplayText(text);
		SwingUtilities.invokeLater(() -> companionStatusLabel.setText(clean));
	}

	private boolean confirmDiscardTransientCompanion() {
		refreshCompanionBinding(false);
		if (activeCompanionZip != null || !companionDirty || conversationTurns.isEmpty())
			return true;

		int result = JOptionPane.showConfirmDialog(this,
				cleanDisplayText("A conversa e os documentos da simulação ainda estão só em memória. Salve o modelo para preservar o arquivo companheiro antes de fechar."),
				cleanDisplayText("Rascunho do assistente não salvo"),
				JOptionPane.OK_CANCEL_OPTION,
				JOptionPane.WARNING_MESSAGE);
		return result == JOptionPane.OK_OPTION;
	}

	private void recordConversationTurn(String speaker, String message) {
		if (restoringConversation)
			return;
		String cleanSpeaker = cleanDisplayText(speaker);
		String cleanMessage = cleanDisplayText(message);
		if (cleanMessage.trim().isEmpty())
			return;

		conversationTurns.add(new ConversationTurn(OffsetDateTime.now().toString(),
				isUserSpeaker(cleanSpeaker) ? "user" : "assistant",
				cleanSpeaker,
				cleanMessage));
		markCompanionDirty();
		persistCompanionIfSaved(false, "chat");
	}

	private static boolean isUserSpeaker(String speaker) {
		String normalized = normalizeForIntent(speaker);
		return normalized.contains("voce") || normalized.contains("usuario") || normalized.contains("operador");
	}

	private void markCompanionDirty() {
		companionDirty = true;
		refreshCompanionBinding(false);
		updateCompanionStatusLabel();
	}

	private Path prepareChatHistoryFileForHelper(String caseId, String currentMessage) throws IOException {
		Path file = getTransientOutputDir("chat").resolve(caseId + "_chat_history.jsonl");
		String currentClean = cleanDisplayText(currentMessage);
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < conversationTurns.size(); i++) {
			ConversationTurn turn = conversationTurns.get(i);
			if (i == conversationTurns.size() - 1 && "user".equals(turn.role) && turn.content.equals(currentClean))
				continue;
			sb.append(turn.toJsonLine()).append(System.lineSeparator());
		}
		Files.write(file, sb.toString().getBytes(StandardCharsets.UTF_8),
				StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
		activeChatHistoryFile = file;
		return file;
	}

	private void captureBriefingArtifacts(Path outputDir, String caseId) {
		try {
			companionBriefingJson = readFileIfExists(outputDir.resolve(caseId + "_briefing_assist.json"));
			companionBriefingMarkdown = readFileIfExists(outputDir.resolve(caseId + "_briefing_assist.md"));
			companionHistoryMarkdown = readFileIfExists(outputDir.resolve(caseId + "_historia_simulacao.md"));
			companionPrdMarkdown = readFileIfExists(outputDir.resolve(caseId + "_prd_interno.md"));
			companionEpicsMarkdown = readFileIfExists(outputDir.resolve(caseId + "_epicos_stories.md"));
			markCompanionDirty();
			persistCompanionIfSaved(false, "briefing");
		}
		catch (IOException ex) {
			appendChatMessage("Assistente", "Gerei o briefing, mas não consegui capturar todos os artefatos para o arquivo companheiro: " + ex.getMessage());
		}
	}

	private static String readFileIfExists(Path file) throws IOException {
		if (!Files.isRegularFile(file))
			return "";
		return new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
	}

	private void persistCompanionIfSaved(boolean backupConfig, String reason) {
		refreshCompanionBinding(false);
		if (activeCompanionZip == null)
			return;
		try {
			Files.createDirectories(activeCompanionZip.getParent());
			writeCompanionZip(activeCompanionZip, reason);
			companionDirty = false;
			if (backupConfig)
				backupCurrentConfigIfChanged();
			updateCompanionStatusLabel();
		}
		catch (IOException ex) {
			appendStatusText(System.lineSeparator()
					+ "Assistente: não consegui salvar o arquivo companheiro: " + ex.getMessage()
					+ System.lineSeparator());
		}
	}

	private void writeCompanionZip(Path zipPath, String reason) throws IOException {
		Path tempZip = zipPath.resolveSibling(zipPath.getFileName().toString() + ".tmp");
		try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(tempZip,
				StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING))) {
			writeZipEntry(zip, "manifest.json", buildCompanionManifest(reason));
			writeZipEntry(zip, "conversation.jsonl", buildConversationJsonl());
			writeZipEntry(zip, "historia_simulacao.md", defaultIfEmpty(companionHistoryMarkdown, "# História da simulação\n\nAinda não gerada.\n"));
			writeZipEntry(zip, "prd_interno.md", defaultIfEmpty(companionPrdMarkdown, "# PRD interno\n\nAinda não gerado.\n"));
			writeZipEntry(zip, "epicos_stories.md", defaultIfEmpty(companionEpicsMarkdown, "# Épicos e stories\n\nAinda não gerados.\n"));
			writeZipEntry(zip, "decisions.json", "[]\n");
			writeZipEntry(zip, "briefing_assist.json", defaultIfEmpty(companionBriefingJson, "{}\n"));
			writeZipEntry(zip, "briefing_assist.md", defaultIfEmpty(companionBriefingMarkdown, "# Briefing\n\nAinda não gerado.\n"));
			writeZipEntry(zip, "respostas_operador.md", defaultIfEmpty(companionBriefingAnswersMarkdown.toString(), "# Respostas do operador\n\nAinda não registradas.\n"));
			writeStatFitCompanionEntries(zip);
			writeAttachmentCompanionEntries(zip);
		}
		try {
			Files.move(tempZip, zipPath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
		}
		catch (IOException ex) {
			Files.move(tempZip, zipPath, StandardCopyOption.REPLACE_EXISTING);
		}
	}

	private String buildCompanionManifest(String reason) throws IOException {
		String modelPath = activeCompanionModelFile == null ? "" : activeCompanionModelFile.getAbsolutePath();
		String modified = "";
		if (activeCompanionModelFile != null && activeCompanionModelFile.isFile())
			modified = Files.getLastModifiedTime(activeCompanionModelFile.toPath()).toString();

		return "{\n"
				+ "  \"schema_version\": 1,\n"
				+ "  \"kind\": \"jaamsim-ai-companion\",\n"
				+ "  \"updated_at\": \"" + jsonEscape(OffsetDateTime.now().toString()) + "\",\n"
				+ "  \"reason\": \"" + jsonEscape(reason) + "\",\n"
				+ "  \"model_file\": \"" + jsonEscape(modelPath) + "\",\n"
				+ "  \"model_last_modified\": \"" + jsonEscape(modified) + "\",\n"
				+ "  \"autosave_minutes\": " + ((Integer) autosaveMinutesSpinner.getValue()).intValue() + ",\n"
				+ "  \"entries\": [\"conversation.jsonl\", \"historia_simulacao.md\", \"prd_interno.md\", \"epicos_stories.md\", \"decisions.json\", \"statfit/README.md\", \"statfit/latest_manifest.json\", \"statfit/latest/\", \"attachments/README.md\", \"attachments/manifest.json\", \"attachments/files/\"]\n"
				+ "}\n";
	}

	private String buildConversationJsonl() {
		StringBuilder sb = new StringBuilder();
		for (ConversationTurn turn : conversationTurns)
			sb.append(turn.toJsonLine()).append(System.lineSeparator());
		return sb.toString();
	}

	private static String defaultIfEmpty(String value, String fallback) {
		if (value == null || value.trim().isEmpty())
			return fallback;
		return value;
	}

	private static void writeZipEntry(ZipOutputStream zip, String name, String content) throws IOException {
		ZipEntry entry = new ZipEntry(name);
		zip.putNextEntry(entry);
		byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
		zip.write(bytes, 0, bytes.length);
		zip.closeEntry();
	}

	private void writeStatFitCompanionEntries(ZipOutputStream zip) throws IOException {
		Path assistantRoot = activeCompanionModelFile == null ? null : findAssistantRoot(activeCompanionModelFile);
		if (assistantRoot == null) {
			writeEmptyStatFitCompanionEntries(zip, "Nenhum diretorio da extensao foi localizado para anexar resultados StatFit.");
			return;
		}

		Path outputDir = assistantRoot.resolve("output")
				.resolve("statfit");
		if (!Files.isDirectory(outputDir)) {
			writeEmptyStatFitCompanionEntries(zip, "A pasta de resultados StatFit ainda nao existe.");
			return;
		}

		List<Path> artifacts = collectLatestStatFitArtifacts(outputDir);
		if (artifacts.isEmpty()) {
			writeEmptyStatFitCompanionEntries(zip, "Nenhum ajuste StatFit foi encontrado para anexar ao arquivo companheiro.");
			return;
		}

		StringBuilder readme = new StringBuilder();
		readme.append("# StatFit\n\n");
		readme.append("Ultimos artefatos StatFit anexados automaticamente ao salvar/autosalvar o arquivo companheiro.\n");
		readme.append("Fonte: ").append(outputDir.toAbsolutePath()).append("\n\n");
		readme.append("Arquivos:\n");
		StringBuilder manifest = new StringBuilder();
		manifest.append("{\n");
		manifest.append("  \"updated_at\": \"").append(jsonEscape(OffsetDateTime.now().toString())).append("\",\n");
		manifest.append("  \"source_dir\": \"").append(jsonEscape(outputDir.toAbsolutePath().toString())).append("\",\n");
		manifest.append("  \"files\": [\n");
		for (int i = 0; i < artifacts.size(); i++) {
			Path artifact = artifacts.get(i);
			String fileName = artifact.getFileName().toString();
			String entryName = "statfit/latest/" + fileName;
			readme.append("- `").append(entryName).append("`\n");
			manifest.append("    \"").append(jsonEscape(entryName)).append("\"");
			if (i + 1 < artifacts.size())
				manifest.append(",");
			manifest.append("\n");
			writeZipFileEntry(zip, entryName, artifact);
		}
		manifest.append("  ]\n");
		manifest.append("}\n");
		writeZipEntry(zip, "statfit/README.md", readme.toString());
		writeZipEntry(zip, "statfit/latest_manifest.json", manifest.toString());
	}

	private static void writeEmptyStatFitCompanionEntries(ZipOutputStream zip, String message) throws IOException {
		writeZipEntry(zip, "statfit/README.md", "# StatFit\n\n" + message + "\n");
		writeZipEntry(zip, "statfit/latest_manifest.json",
				"{\n"
				+ "  \"updated_at\": \"" + jsonEscape(OffsetDateTime.now().toString()) + "\",\n"
				+ "  \"status\": \"" + jsonEscape(message) + "\",\n"
				+ "  \"files\": []\n"
				+ "}\n");
	}

	private static List<Path> collectLatestStatFitArtifacts(Path outputDir) throws IOException {
		Path latestJson = findLatestStatFitArtifact(outputDir, "_statfit_report.json");
		Path latestMarkdown = findLatestStatFitArtifact(outputDir, "_statfit_report.md");
		Path anchor = newerPath(latestJson, latestMarkdown);
		if (anchor == null)
			return Collections.emptyList();

		String anchorName = anchor.getFileName().toString();
		String prefix = stripStatFitReportSuffix(anchorName);
		if (prefix == null || prefix.isEmpty())
			return Collections.emptyList();

		String[] suffixes = {
				"_statfit_report.md",
				"_statfit_report.json",
				"_jaamsim_distribution.cfg",
				"_histograma.svg",
				"_cdf_empirica.svg",
				"_qq_plot.svg",
				"_pp_plot.svg"
		};

		ArrayList<Path> files = new ArrayList<>();
		for (String suffix : suffixes) {
			Path candidate = outputDir.resolve(prefix + suffix);
			if (Files.isRegularFile(candidate))
				files.add(candidate);
		}
		return files;
	}

	private static String stripStatFitReportSuffix(String fileName) {
		String jsonSuffix = "_statfit_report.json";
		String markdownSuffix = "_statfit_report.md";
		if (fileName.endsWith(jsonSuffix))
			return fileName.substring(0, fileName.length() - jsonSuffix.length());
		if (fileName.endsWith(markdownSuffix))
			return fileName.substring(0, fileName.length() - markdownSuffix.length());
		return null;
	}

	private static Path newerPath(Path first, Path second) throws IOException {
		if (first == null)
			return second;
		if (second == null)
			return first;
		FileTime firstTime = Files.getLastModifiedTime(first);
		FileTime secondTime = Files.getLastModifiedTime(second);
		return firstTime.compareTo(secondTime) >= 0 ? first : second;
	}

	private static Path findLatestStatFitArtifact(Path outputDir, String suffix) throws IOException {
		Path latest = null;
		FileTime latestTime = null;
		try (java.util.stream.Stream<Path> paths = Files.list(outputDir)) {
			for (Path path : (Iterable<Path>) paths::iterator) {
				if (!Files.isRegularFile(path) || !path.getFileName().toString().endsWith(suffix))
					continue;
				FileTime modified = Files.getLastModifiedTime(path);
				if (latest == null || modified.compareTo(latestTime) > 0) {
					latest = path;
					latestTime = modified;
				}
			}
		}
		return latest;
	}

	private static void writeZipFileEntry(ZipOutputStream zip, String name, Path file) throws IOException {
		ZipEntry entry = new ZipEntry(name);
		zip.putNextEntry(entry);
		Files.copy(file, zip);
		zip.closeEntry();
	}

	private void writeAttachmentCompanionEntries(ZipOutputStream zip) throws IOException {
		StringBuilder readme = new StringBuilder();
		StringBuilder manifest = new StringBuilder();
		readme.append("# Anexos\n\n");
		manifest.append("{\n");
		manifest.append("  \"updated_at\": \"").append(jsonEscape(OffsetDateTime.now().toString())).append("\",\n");
		manifest.append("  \"status\": \"attachments_registered\",\n");
		manifest.append("  \"files\": [\n");

		int written = 0;
		for (AttachmentRecord attachment : companionAttachments) {
			Path source = Paths.get(attachment.storedPath);
			if (!Files.isRegularFile(source))
				continue;
			String entryName = "attachments/files/" + attachment.storedName;
			if (written > 0)
				manifest.append(",\n");
			manifest.append("    {")
					.append("\"entry\": \"").append(jsonEscape(entryName)).append("\", ")
					.append("\"original_name\": \"").append(jsonEscape(attachment.originalName)).append("\", ")
					.append("\"kind\": \"").append(jsonEscape(attachment.kind)).append("\", ")
					.append("\"size_bytes\": ").append(attachment.sizeBytes)
					.append("}");
			readme.append("- `").append(entryName).append("`");
			if (!attachment.originalName.equals(attachment.storedName))
				readme.append(" (origem: ").append(attachment.originalName).append(")");
			readme.append("\n");
			writeZipFileEntry(zip, entryName, source);
			written++;
		}

		if (written == 0)
			readme.append("Nenhum anexo registrado nesta sessao.\n");
		manifest.append("\n  ]\n");
		manifest.append("}\n");
		writeZipEntry(zip, "attachments/README.md", readme.toString());
		writeZipEntry(zip, "attachments/manifest.json", manifest.toString());
	}

	private void loadCompanionZip(Path zipPath) {
		ArrayList<ConversationTurn> loadedTurns = new ArrayList<>();
		try (ZipInputStream zip = new ZipInputStream(Files.newInputStream(zipPath))) {
			ZipEntry entry;
			while ((entry = zip.getNextEntry()) != null) {
				String entryName = entry.getName();
				if (entryName.startsWith("attachments/files/")) {
					restoreAttachmentFromZip(zip, entryName);
					zip.closeEntry();
					continue;
				}
				String content = readZipEntryText(zip);
				if ("conversation.jsonl".equals(entryName)) {
					loadedTurns.addAll(parseConversationJsonl(content));
				}
				else if ("historia_simulacao.md".equals(entryName)) {
					companionHistoryMarkdown = content;
				}
				else if ("prd_interno.md".equals(entryName)) {
					companionPrdMarkdown = content;
				}
				else if ("epicos_stories.md".equals(entryName)) {
					companionEpicsMarkdown = content;
				}
				else if ("briefing_assist.json".equals(entryName)) {
					companionBriefingJson = content;
				}
				else if ("briefing_assist.md".equals(entryName)) {
					companionBriefingMarkdown = content;
				}
				else if ("respostas_operador.md".equals(entryName)) {
					companionBriefingAnswersMarkdown.setLength(0);
					companionBriefingAnswersMarkdown.append(content);
				}
				zip.closeEntry();
			}
		}
		catch (IOException ex) {
			appendStatusText(System.lineSeparator()
					+ "Assistente: encontrei o arquivo companheiro, mas não consegui carregá-lo: "
					+ ex.getMessage() + System.lineSeparator());
			return;
		}

		if (!loadedTurns.isEmpty()) {
			conversationTurns.clear();
			conversationTurns.addAll(loadedTurns);
			restoreConversationDisplay();
		}
	}

	private static String readZipEntryText(ZipInputStream zip) throws IOException {
		ByteArrayOutputStream output = new ByteArrayOutputStream();
		byte[] buffer = new byte[4096];
		int read;
		while ((read = zip.read(buffer)) >= 0) {
			if (read > 0)
				output.write(buffer, 0, read);
		}
		return new String(output.toByteArray(), StandardCharsets.UTF_8);
	}

	private static ArrayList<ConversationTurn> parseConversationJsonl(String content) {
		ArrayList<ConversationTurn> turns = new ArrayList<>();
		for (String line : content.split("\\R")) {
			String trimmed = line.trim();
			if (trimmed.isEmpty())
				continue;
			try {
				JSONValue root = JSONParser.parse(trimmed);
				String timestamp = getStringChild(root, "timestamp", "");
				String role = getStringChild(root, "role", "assistant");
				String speaker = getStringChild(root, "speaker", "Assistente");
				String turnContent = getStringChild(root, "content", "");
				if (!turnContent.trim().isEmpty())
					turns.add(new ConversationTurn(timestamp, role, speaker, turnContent));
			}
			catch (Exception ignored) {
				// Ignore corrupt historical lines and keep loading the rest.
			}
		}
		return turns;
	}

	private void restoreConversationDisplay() {
		StringBuilder sb = new StringBuilder();
		restoringConversation = true;
		for (ConversationTurn turn : conversationTurns) {
			sb.append(turn.speaker).append(": ").append(turn.content).append(System.lineSeparator()).append(System.lineSeparator());
		}
		setStatusText(sb.toString());
		welcomeShown = true;
		restoringConversation = false;
	}

	private void backupCurrentConfigIfChanged() throws IOException {
		if (activeCompanionModelFile == null || !activeCompanionModelFile.isFile())
			return;

		Path cfgPath = activeCompanionModelFile.toPath();
		FileTime modified = Files.getLastModifiedTime(cfgPath);
		if (lastBackedUpConfigTime != null && lastBackedUpConfigTime.equals(modified))
			return;

		Path backupDir = cfgPath.toAbsolutePath().getParent().resolve(".jaamsim-ai-backups");
		Files.createDirectories(backupDir);
		String modelId = buildModelId(activeCompanionModelFile);
		String timestamp = OffsetDateTime.now().toString().replaceAll("[^0-9A-Za-z]+", "_");
		Path backupFile = backupDir.resolve(modelId + "_autosave_" + timestamp + ".cfg");
		Files.copy(cfgPath, backupFile, StandardCopyOption.REPLACE_EXISTING);
		lastBackedUpConfigTime = modified;
	}

	private static String jsonEscape(String value) {
		if (value == null)
			return "";
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < value.length(); i++) {
			char ch = value.charAt(i);
			switch (ch) {
			case '\\':
				sb.append("\\\\");
				break;
			case '"':
				sb.append("\\\"");
				break;
			case '\n':
				sb.append("\\n");
				break;
			case '\r':
				sb.append("\\r");
				break;
			case '\t':
				sb.append("\\t");
				break;
			default:
				if (ch < 0x20)
					sb.append(String.format("\\u%04x", (int) ch));
				else
					sb.append(ch);
				break;
			}
		}
		return sb.toString();
	}

	private static String sanitizeFileName(String value) {
		String name = value == null ? "attachment" : value.trim();
		name = name.replace('\\', '_').replace('/', '_').replace(':', '_')
				.replace('*', '_').replace('?', '_').replace('"', '_')
				.replace('<', '_').replace('>', '_').replace('|', '_');
		name = name.replaceAll("\\s+", "_").replaceAll("_+", "_");
		if (name.isEmpty())
			name = "attachment";
		if (name.length() > 96)
			name = name.substring(name.length() - 96);
		return name;
	}

	private static String inferAttachmentKind(String fileName) {
		String lower = fileName == null ? "" : fileName.toLowerCase(Locale.ROOT);
		if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg")
				|| lower.endsWith(".gif") || lower.endsWith(".bmp") || lower.endsWith(".svg"))
			return "imagem";
		if (lower.endsWith(".bpmn") || lower.endsWith(".vsdx") || lower.endsWith(".xml"))
			return "fluxo/diagrama";
		if (lower.endsWith(".csv") || lower.endsWith(".txt") || lower.endsWith(".xlsx"))
			return "dados";
		if (lower.endsWith(".pdf"))
			return "documento";
		return "arquivo";
	}

	private void handleChatSubmit() {
		String message = ideaArea.getText() == null ? "" : ideaArea.getText().trim();
		if (message.isEmpty())
			return;

		ideaArea.setText("");
		appendChatMessage("Você", message);
		String normalized = normalizeForIntent(message);

		if (guidedBriefingActive && containsAny(normalized, "gerar agora", "criar agora", "finalizar briefing", "gerar briefing", "criar prd")) {
			finishGuidedBriefing();
			return;
		}

		if (guidedBriefingActive && !looksLikeCommand(normalized)) {
			handleGuidedBriefingAnswer(message);
			return;
		}

		if (hasPendingBriefingQuestion() && !looksLikeCommand(normalized)) {
			handlePendingBriefingAnswer(message);
			return;
		}

		if (isExplicitReviewHistoryIntent(normalized)) {
			appendChatMessage("Assistente", "Vou consultar o histórico local de revisões, sem executar a análise novamente.");
			showReviewHistory();
			return;
		}

		if (isExplicitReviewIntent(normalized)) {
			appendChatMessage("Assistente", "Vou revisar o modelo salvo com as regras locais. Se o modelo ainda não foi salvo como .cfg, o JaamSim vai pedir esse passo primeiro.");
			runLocalRcl();
			return;
		}

		if (isExplicitSuggestionListIntent(normalized)) {
			appendChatMessage("Assistente", "Vou mostrar as sugestões mais recentes registradas pela revisão local.");
			showLatestSuggestions();
			return;
		}

		if (isExplicitAcceptSuggestionIntent(normalized)) {
			appendChatMessage("Assistente", "Vou registrar aceite na primeira sugestão pendente. Isso não altera o modelo automaticamente.");
			updateFirstPendingSuggestion("accepted");
			return;
		}

		if (isExplicitRejectSuggestionIntent(normalized)) {
			appendChatMessage("Assistente", "Vou registrar rejeição na primeira sugestão pendente.");
			updateFirstPendingSuggestion("rejected");
			return;
		}

		if (isExplicitStatFitIntent(normalized)) {
			appendChatMessage("Assistente", "Vou abrir o StatFit auxiliar. Use-o para importar dados numéricos e estimar distribuições candidatas.");
			openStatFitAssistant();
			return;
		}

		if (containsAny(normalized, "abrir briefing", "pasta briefing")) {
			appendChatMessage("Assistente", "Vou abrir a pasta dos documentos de briefing e PRD interno.");
			openBriefingOutputFolder();
			return;
		}

		if (containsAny(normalized, "abrir resultado", "pasta resultado", "abrir pasta")) {
			appendChatMessage("Assistente", "Vou abrir a pasta de resultados da revisão local.");
			openRclOutputFolder();
			return;
		}

		if (containsAny(normalized, "config", "notific", "cooldown", "autocorrec")) {
			appendChatMessage("Assistente", "As configurações ficam na aba Configurações. Ali você controla notificações, cooldown, IA online e autocorreção experimental.");
			return;
		}

		if (autoCorrectionCheckBox.isSelected() && containsAny(normalized, "corrigir", "corrija", "aplicar")) {
			appendChatMessage("Assistente", "A autocorreção experimental está ligada, mas nesta etapa eu apenas preparo correções seguras. Aplicação automática de valores entra em uma sprint própria.");
			return;
		}

		if (onlineAiCheckBox.isSelected()) {
			runOnlineChatAssist(message);
			return;
		}

		if (isGreeting(normalized)) {
			appendChatMessage("Assistente", buildGreetingResponse());
			return;
		}

		if (containsAny(normalized, "dica", "ajuda", "auxilie", "orienta", "proximo passo", "proximos passos", "como continuo", "como sigo", "avance", "avancar", "o que faco")) {
			appendChatMessage("Assistente", buildContextualTipResponse());
			return;
		}

		if (isDistributionDiscussion(normalized)) {
			appendChatMessage("Assistente", buildDistributionHeuristicResponse(message));
			return;
		}

		if (isSimulationBuildIntent(normalized)) {
			startGuidedBriefing(message);
			return;
		}

		appendChatMessage("Assistente", "Entendi. Para eu te ajudar melhor dentro do JaamSim, vou começar com uma pergunta objetiva.");
		startGuidedBriefing(message);
	}

	private static String normalizeForIntent(String value) {
		if (value == null || value.isEmpty())
			return "";
		String normalized = Normalizer.normalize(normalizeUtf8Text(value), Normalizer.Form.NFD);
		normalized = normalized.replaceAll("\\p{M}", "");
		return normalized.toLowerCase(Locale.ROOT).trim();
	}

	private static boolean isGreeting(String value) {
		String cleaned = value.trim();
		return cleaned.equals("oi") || cleaned.equals("ola") || cleaned.equals("olá")
				|| cleaned.equals("bom dia") || cleaned.equals("boa tarde") || cleaned.equals("boa noite")
				|| cleaned.equals("e ai") || cleaned.equals("e aí");
	}

	private static boolean looksLikeCommand(String value) {
		return isExplicitReviewHistoryIntent(value)
				|| isExplicitReviewIntent(value)
				|| isExplicitSuggestionListIntent(value)
				|| isExplicitAcceptSuggestionIntent(value)
				|| isExplicitRejectSuggestionIntent(value)
				|| containsAny(value, "statfit",
				"distribuic", "csv", "dados", "abrir", "pasta", "config", "notific", "cooldown",
				"autocorrec", "dica", "ajuda", "proximo passo", "proximos passos");
	}

	private static boolean isExplicitReviewHistoryIntent(String value) {
		return containsAny(value, "historico rcl", "historico de revisao",
				"historico de revisoes", "mostrar historico", "listar revisoes",
				"ultimas revisoes", "ver revisoes", "revisoes anteriores");
	}

	private static boolean isExplicitReviewIntent(String value) {
		return containsAny(value, "revisar modelo", "revise meu modelo", "analisar modelo",
				"analise meu modelo", "diagnosticar modelo", "rodar revisao", "rodar revisão",
				"checar modelo", "verificar modelo", "explicar alerta", "explique este alerta");
	}

	private static boolean isExplicitSuggestionListIntent(String value) {
		return containsAny(value, "mostrar sugestoes", "mostrar sugestões", "ver sugestoes", "ver sugestões",
				"listar sugestoes", "listar sugestões", "sugestoes da revisao", "sugestões da revisão",
				"sugestoes rcl", "sugestões rcl");
	}

	private static boolean isExplicitAcceptSuggestionIntent(String value) {
		return containsAny(value, "aceitar sugestao", "aceitar sugestão", "aceitar primeira sugestao",
				"aceitar primeira sugestão", "aprovar sugestao", "aprovar sugestão", "aceitar rcl",
				"aprovar rcl", "aceitar alerta", "aprovar alerta");
	}

	private static boolean isExplicitRejectSuggestionIntent(String value) {
		return containsAny(value, "rejeitar sugestao", "rejeitar sugestão", "rejeitar primeira sugestao",
				"rejeitar primeira sugestão", "recusar sugestao", "recusar sugestão", "rejeitar rcl",
				"recusar rcl", "rejeitar alerta", "recusar alerta");
	}

	private static boolean isExplicitStatFitIntent(String value) {
		return containsAny(value, "abrir statfit", "abra statfit", "rodar statfit", "executar statfit",
				"ajustar no statfit", "importar csv", "carregar csv", "tenho csv", "arquivo csv",
				"usar arquivo de dados", "importar dados numericos", "importar dados num");
	}

	private static boolean isDistributionDiscussion(String value) {
		return containsAny(value, "qual distribuic", "sugerir distribuic", "distribuicao correta",
				"distribu", "sem dados", "nao tenho dados", "não tenho dados",
				"chegadas aleatorias", "chegadas aleat", "vendas aleatorias", "vendas aleat",
				"podemos usar qualquer", "taxa de chegada", "padrao de chegada", "padrão de chegada");
	}

	private static boolean isSimulationBuildIntent(String value) {
		return containsAny(value, "construir", "criar", "montar", "modelar", "modelo", "simulacao",
				"simulação", "simular", "representar", "processo", "fluxo", "prd", "briefing");
	}

	private String buildGreetingResponse() {
		return "Oi! Estou aqui para te ajudar a montar ou revisar uma simulação. "
				+ "Podemos começar do zero, revisar o modelo salvo, explicar um alerta ou preparar dados no StatFit. "
				+ "Se quiser construir uma simulação, me diga primeiro qual processo você quer representar.";
	}

	private static String buildDistributionHeuristicResponse(String message) {
		return "Sem amostra histórica, eu trataria a distribuição como hipótese de modelagem e validaria por cenários. "
				+ "Para chegadas ou vendas aleatórias, uma boa primeira opção costuma ser processo de Poisson, com tempos entre chegadas exponenciais; "
				+ "se você tiver apenas uma faixa de tempo de processo, use uniforme ou triangular; se o lote for fixo, modele como valor determinístico. "
				+ "No seu caso, eu separaria vendas/chegadas, reposição do estoque e tempo de fritura. Qual é o tempo de expediente usado para transformar as 60 coxinhas por dia em taxa?";
	}

	private void startGuidedBriefing(String seed) {
		guidedBriefingActive = true;
		guidedBriefingSeed = seed;
		guidedBriefingAnswers.clear();
		pendingBriefingQuestions.clear();
		briefingAnswers.clear();
		appendChatMessage("Assistente",
				"Perfeito. Vamos construir isso juntos, sem gerar documento genérico antes da hora. "
						+ GUIDED_BRIEFING_QUESTIONS[0]);
	}

	private void handleGuidedBriefingAnswer(String message) {
		guidedBriefingAnswers.add(message);
		int nextIndex = guidedBriefingAnswers.size();
		if (nextIndex < GUIDED_BRIEFING_QUESTIONS.length) {
			appendChatMessage("Assistente", "Entendi. " + GUIDED_BRIEFING_QUESTIONS[nextIndex]);
			return;
		}
		finishGuidedBriefing();
	}

	private void finishGuidedBriefing() {
		if (!guidedBriefingActive && guidedBriefingAnswers.isEmpty())
			return;

		guidedBriefingActive = false;
		String idea = buildGuidedBriefingIdea();
		appendChatMessage("Assistente",
				"Fechado. Agora tenho contexto suficiente para montar a primeira versao do briefing e do PRD interno. Depois disso a gente continua refinando.");
		runBriefingAssist(idea);
	}

	private String buildGuidedBriefingIdea() {
		StringBuilder sb = new StringBuilder();
		sb.append(guidedBriefingSeed == null ? "" : guidedBriefingSeed.trim());
		for (int i = 0; i < guidedBriefingAnswers.size(); i++) {
			sb.append(System.lineSeparator());
			sb.append("Pergunta: ").append(GUIDED_BRIEFING_QUESTIONS[i]).append(System.lineSeparator());
			sb.append("Resposta: ").append(guidedBriefingAnswers.get(i));
		}
		return sb.toString().trim();
	}

	private void runOnlineChatAssist(String message) {
		Thread worker = new Thread(() -> runOnlineChatAssistWorker(message), "JaamSim AI Assistant Chat LLM");
		worker.setDaemon(true);
		worker.start();
	}

	private void runOnlineChatAssistWorker(String message) {
		try {
			JaamSimModel simModel = GUIFrame.getJaamSimModel();
			File anchorFile = new File(".");
			if (simModel != null && simModel.getConfigFile() != null)
				anchorFile = simModel.getConfigFile();

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				startGuidedBriefing(message);
				return;
			}

			Path script = assistantRoot.resolve("python").resolve("simulation_chat_assist.py");
			if (!Files.isRegularFile(script)) {
				startGuidedBriefing(message);
				return;
			}

			refreshCompanionBinding(false);
			Path outputDir = getTransientOutputDir("chat");
			String caseId = getOrCreateChatCaseId(anchorFile);
			Path historyFile = prepareChatHistoryFileForHelper(caseId, message);
			List<String> command = buildChatCommand(script, outputDir, historyFile, caseId, message,
					buildModelContextText(simModel));
			RclRunResult result = executeCommand(command, assistantRoot, RCL_TIMEOUT_SECONDS);
			if (result.finished && result.exitCode == 0 && !result.output.trim().isEmpty()) {
				JSONValue root = JSONParser.parse(result.output.trim());
				String response = getStringChild(root, "response", "");
				boolean online = getBooleanChild(root, "online", false);
				if (online && !response.trim().isEmpty()) {
					appendChatMessage("Assistente", response.trim());
					return;
				}
			}
			appendOnlineChatUnavailableMessage();
		}
		catch (Exception ex) {
			appendOnlineChatUnavailableMessage();
		}
	}

	private void appendOnlineChatUnavailableMessage() {
		appendChatMessage("Assistente",
				"Não consegui acessar a IA de conversa neste envio. Confira internet e tokens na aba Configurações; quando estiver ok, me envie a mensagem novamente.");
	}

	private String getOrCreateChatCaseId(File anchorFile) {
		if (anchorFile != null && anchorFile.isFile()) {
			activeChatCaseId = buildModelId(anchorFile);
			return activeChatCaseId;
		}
		if (activeChatCaseId != null)
			return activeChatCaseId;
		if (activeChatCaseId == null || activeChatCaseId.trim().isEmpty())
			activeChatCaseId = "native_chat_" + System.currentTimeMillis();
		return activeChatCaseId;
	}

	private Path getOrCreateChatHistoryFile(Path outputDir, String caseId) {
		if (activeChatHistoryFile == null)
			activeChatHistoryFile = outputDir.resolve(caseId + "_chat_history.jsonl");
		return activeChatHistoryFile;
	}

	private String buildModelContextText(JaamSimModel simModel) {
		if (simModel == null)
			return "Nenhum modelo JaamSim ativo foi encontrado.";
		ArrayList<Entity> userEntities = collectUserEntities(simModel);
		Map<String, Integer> classCounts = countClasses(userEntities);
		StringBuilder sb = new StringBuilder();
		sb.append("Modelo: ").append(simModel.getName()).append(System.lineSeparator());
		sb.append("Entidades no modelo: ").append(simModel.getEntityCount()).append(System.lineSeparator());
		sb.append("Entidades visiveis analisadas: ").append(userEntities.size()).append(System.lineSeparator());
		sb.append("Arquivo salvo: ").append(simModel.getConfigFile() == null ? "não" : "sim").append(System.lineSeparator());
		String proactive = buildProactiveMessage(classCounts, countReferences(userEntities));
		if (proactive != null)
			sb.append("Sinal local: ").append(proactive).append(System.lineSeparator());
		if (!companionAttachments.isEmpty()) {
			sb.append("Anexos registrados no assistente: ").append(companionAttachments.size()).append(System.lineSeparator());
			int count = 0;
			for (AttachmentRecord attachment : companionAttachments) {
				if (count >= 5)
					break;
				sb.append("- ").append(attachment.originalName)
						.append(" [").append(attachment.kind).append("]")
						.append(System.lineSeparator());
				count++;
			}
		}
		return sb.toString();
	}

	private boolean hasPendingBriefingQuestion() {
		return briefingAnswers.size() < pendingBriefingQuestions.size();
	}

	private void handlePendingBriefingAnswer(String message) {
		int questionIndex = briefingAnswers.size();
		String question = pendingBriefingQuestions.get(questionIndex);
		briefingAnswers.add(message);
		appendBriefingAnswer(questionIndex + 1, question, message);

		if (hasPendingBriefingQuestion()) {
			String nextQuestion = pendingBriefingQuestions.get(briefingAnswers.size());
			appendChatMessage("Assistente", "Perfeito, registrei. Próxima pergunta: " + nextQuestion);
			return;
		}

		appendChatMessage("Assistente",
				"Fechado, registrei as respostas principais. Agora eu sugiro construir o fluxo mínimo no JaamSim: chegada, fila/estoque, processo e saída. Depois disso, peça 'revisar modelo' para eu checar os pontos básicos.");
	}

	private void appendBriefingAnswer(int index, String question, String answer) {
		if (storeBriefingAnswerInMemory(index, question, answer))
			return;

		if (activeBriefingOutputDir == null || activeBriefingCaseId == null)
			return;

		try {
			Files.createDirectories(activeBriefingOutputDir);
			Path answerFile = activeBriefingOutputDir.resolve(activeBriefingCaseId + "_respostas_operador.md");
			StringBuilder sb = new StringBuilder();
			sb.append("## Resposta ").append(index).append(System.lineSeparator());
			sb.append("- Pergunta: ").append(question).append(System.lineSeparator());
			sb.append("- Resposta: ").append(answer).append(System.lineSeparator());
			sb.append("- Registrado em: ").append(OffsetDateTime.now()).append(System.lineSeparator());
			sb.append(System.lineSeparator());
			Files.write(answerFile, sb.toString().getBytes(StandardCharsets.UTF_8),
					StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		}
		catch (IOException ex) {
			appendChatMessage("Assistente", "Consegui seguir a conversa, mas não consegui registrar essa resposta no arquivo: "
					+ ex.getMessage());
		}
	}

	private static boolean containsAny(String value, String... fragments) {
		for (String fragment : fragments) {
			if (value.contains(fragment))
				return true;
		}
		return false;
	}

	private void appendChatMessage(String speaker, String message) {
		recordConversationTurn(speaker, message);
		appendStatusText(System.lineSeparator() + speaker + ": " + message + System.lineSeparator());
	}

	private void setOrAppendConversation(String text) {
		String cleanText = cleanDisplayText(text);
		if (statusArea.getText().trim().isEmpty()) {
			setStatusText(cleanText);
			chatScrollPane.getVerticalScrollBar().setValue(0);
		}
		else {
			appendRichText(System.lineSeparator() + cleanText);
			scrollChatToEnd();
		}
	}

	private boolean storeBriefingAnswerInMemory(int index, String question, String answer) {
		companionBriefingAnswersMarkdown.append("## Resposta ").append(index).append(System.lineSeparator());
		companionBriefingAnswersMarkdown.append("- Pergunta: ").append(question).append(System.lineSeparator());
		companionBriefingAnswersMarkdown.append("- Resposta: ").append(answer).append(System.lineSeparator());
		companionBriefingAnswersMarkdown.append("- Registrado em: ").append(OffsetDateTime.now()).append(System.lineSeparator());
		companionBriefingAnswersMarkdown.append(System.lineSeparator());
		markCompanionDirty();
		persistCompanionIfSaved(false, "briefing-answer");
		return true;
	}

	private void maybeShowAssistantNotification(String message) {
		if (!notificationsCheckBox.isSelected() || !proactiveCheckBox.isSelected())
			return;

		long now = System.currentTimeMillis();
		long cooldownMs = ((Integer) cooldownSpinner.getValue()).intValue() * 1000L;
		if (now - lastNotificationMillis < cooldownMs)
			return;

		lastNotificationMillis = now;
		GUIFrame.showAIAssistantNotification(message);
	}

	private void openStatFitAssistant() {
		StatFitAssistantBox box = StatFitAssistantBox.getInstance();
		box.setVisible(true);
		box.toFront();
	}

	private String buildContextualTipResponse() {
		StringBuilder sb = new StringBuilder();
		sb.append(System.lineSeparator());
		sb.append("Assistente: claro. Aqui vão dicas práticas para avançar agora:").append(System.lineSeparator());

		JaamSimModel simModel = GUIFrame.getJaamSimModel();
		if (simModel == null) {
			sb.append("- Abra ou crie uma simulação para eu analisar o contexto real do modelo.").append(System.lineSeparator());
			sb.append("- Se você ainda estiver na ideia, descreva objetivo, entradas, processo, saídas e métricas esperadas.").append(System.lineSeparator());
			sb.append("- Exemplo: 'quero simular uma máquina com chegada a cada 1:30 minuto, processamento de 1 minuto e estoque máximo de 10'.").append(System.lineSeparator());
			return sb.toString();
		}

		File cfg = simModel.getConfigFile();
		ArrayList<Entity> userEntities = collectUserEntities(simModel);
		Map<String, Integer> classCounts = countClasses(userEntities);
		int referenceCount = countReferences(userEntities);
		String proactiveMessage = buildProactiveMessage(classCounts, referenceCount);

		if (cfg == null) {
			sb.append("- Salve o modelo como .cfg antes da revisão completa; isso permite gerar evidências e sugestões rastreáveis.").append(System.lineSeparator());
		}
		if (proactiveMessage != null) {
			sb.append("- ").append(proactiveMessage).append(System.lineSeparator());
		}
		if (getCount(classCounts, "EntityGenerator") == 0 && getCount(classCounts, "EntityGen") == 0) {
			sb.append("- Defina como as entidades entram no sistema: chegada constante, tabela de dados ou distribuição.").append(System.lineSeparator());
		}
		if (getCount(classCounts, "Queue") == 0) {
			sb.append("- Se existir espera, represente-a explicitamente com fila ou estoque intermediário.").append(System.lineSeparator());
		}
		if (getCount(classCounts, "Server") == 0 && getCount(classCounts, "EntityProcessor") == 0) {
			sb.append("- Se existir transformação/atendimento, modele o recurso ou processo que consome tempo.").append(System.lineSeparator());
		}
		if (getCount(classCounts, "EntitySink") == 0) {
			sb.append("- Garanta uma saída do sistema para medir produção, lead time e gargalos.").append(System.lineSeparator());
		}
		if (referenceCount == 0) {
			sb.append("- Confira conexões/referências entre objetos antes de rodar cenários; modelo sem ligações costuma simular pouco.").append(System.lineSeparator());
		}

		sb.append("- Para tempos medidos, abra o StatFit e importe CSV/TXT com uma coluna numérica.").append(System.lineSeparator());
		sb.append("- Para apoio de concepção, escreva sua ideia completa e eu organizo história, PRD interno, épicos/stories e perguntas.").append(System.lineSeparator());
		sb.append("- Para checagem local, escreva 'revisar modelo'. Para decidir sugestões, escreva 'aceitar sugestão' ou 'rejeitar sugestão'.").append(System.lineSeparator());
		return sb.toString();
	}

	private static String buildProactiveMessage(Map<String, Integer> classCounts, int referenceCount) {
		if (getCount(classCounts, "Queue") > 0 && getCount(classCounts, "Server") == 0
				&& getCount(classCounts, "EntityProcessor") == 0) {
			return "Notei fila no modelo, mas ainda não encontrei servidor/processador. Talvez falte representar quem atende essa fila.";
		}
		if (getCount(classCounts, "EntityGenerator") == 0 && getCount(classCounts, "EntityGen") == 0) {
			return "Ainda não encontrei gerador de entidades. Se o modelo precisa de chegadas, vale revisar esse ponto.";
		}
		if (getCount(classCounts, "EntitySink") == 0) {
			return "Ainda não encontrei uma saída do sistema. Simulações de fluxo geralmente precisam de um destino final.";
		}
		if (referenceCount == 0) {
			return "Não encontrei referências entre entidades nos inputs analisados. Pode ser um modelo inicial, mas vale conferir conexões e relacionamentos.";
		}
		return null;
	}

	private void runLocalRcl() {
		appendStatusText(System.lineSeparator() + System.lineSeparator()
				+ "Assistente: iniciando revisão local offline..." + System.lineSeparator());

		Thread worker = new Thread(() -> runLocalRclWorker(), "JaamSim AI Assistant Local RCL");
		worker.setDaemon(true);
		worker.start();
	}

	private void runBriefingAssist() {
		String idea = ideaArea.getText() == null ? "" : ideaArea.getText().trim();
		runBriefingAssist(idea);
	}

	private void runBriefingAssist(String idea) {
		if (idea.length() < 20) {
			appendStatusText(System.lineSeparator() + System.lineSeparator()
					+ "Assistente: descreva a ideia da simulação com pelo menos 20 caracteres." + System.lineSeparator());
			return;
		}

		boolean useOnlineAi = onlineAiCheckBox.isSelected();
		appendStatusText(System.lineSeparator() + System.lineSeparator()
				+ "Assistente: vou preparar história, PRD interno e épicos/stories com base no que conversamos."
				+ System.lineSeparator());

		Thread worker = new Thread(() -> runBriefingAssistWorker(idea, useOnlineAi), "JaamSim AI Assistant Briefing");
		worker.setDaemon(true);
		worker.start();
	}

	private void runBriefingAssistWorker(String idea, boolean useOnlineAi) {
		try {
			JaamSimModel simModel = GUIFrame.getJaamSimModel();
			File anchorFile = new File(".");
			if (simModel != null && simModel.getConfigFile() != null)
				anchorFile = simModel.getConfigFile();

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText("Assistente: não encontrei a pasta da extensao academica." + System.lineSeparator()
						+ "Configure JAAMSIM_ASSISTANT_ROOT ou jaamsim.assistant.root apontando para extensions/academic-assistant." + System.lineSeparator());
				return;
			}

			Path script = assistantRoot.resolve("python").resolve("simulation_briefing_assist.py");
			if (!Files.isRegularFile(script)) {
				appendStatusText("Assistente: script de briefing não encontrado: "
						+ script.toAbsolutePath() + System.lineSeparator());
				return;
			}

			refreshCompanionBinding(false);
			Path outputDir = getTransientOutputDir("briefing");
			String caseId = buildBriefingCaseId(anchorFile, idea);
			List<String> command = buildBriefingCommand(script, outputDir, caseId, idea, useOnlineAi);

			appendChatMessage("Assistente", "Combinado. Vou organizar isso em documentos de apoio e, em seguida, te fazer uma pergunta por vez para refinar a simulação.");

			RclRunResult result = executeCommand(command, assistantRoot, RCL_TIMEOUT_SECONDS);
			Path briefingJson = outputDir.resolve(caseId + "_briefing_assist.json");
			if (result.finished && result.exitCode == 0 && Files.isRegularFile(briefingJson)) {
				captureBriefingArtifacts(outputDir, caseId);
				appendStatusText(buildBriefingChatSummary(briefingJson, outputDir, useOnlineAi, caseId));
			}
			else {
				appendStatusText(buildBriefingFailureSummary(result));
			}
		}
		catch (Exception ex) {
			appendStatusText("Erro no briefing: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private void runLocalRclWorker() {
		try {
			JaamSimModel simModel = GUIFrame.getJaamSimModel();
			if (simModel == null || simModel.getConfigFile() == null) {
				appendStatusText("Assistente: salve o modelo como .cfg antes da revisão." + System.lineSeparator());
				return;
			}
			File cfgFile = simModel.getConfigFile();
			if (!cfgFile.isFile()) {
				appendStatusText("Assistente: CFG não encontrado: " + cfgFile.getAbsolutePath() + System.lineSeparator());
				return;
			}

			Path assistantRoot = findAssistantRoot(cfgFile);
			if (assistantRoot == null) {
				appendStatusText("Assistente: raiz da extensão não encontrada. Configure JAAMSIM_ASSISTANT_ROOT."
						+ System.lineSeparator());
				return;
			}

			Path script = assistantRoot.resolve("python").resolve("modulo_ia_offline.py");
			if (!Files.isRegularFile(script)) {
				appendStatusText("Assistente: motor RCL não encontrado: " + script + System.lineSeparator());
				return;
			}
			String modelId = buildModelId(cfgFile);
			Path outputRoot = getRclOutputRoot(assistantRoot);
			// Import only decisions tied to the SAME physical CFG and SAME content hash.
			String beforeSha = sha256File(cfgFile.toPath());
			Path priorStatus = findSuggestionStatusFile(outputRoot, cfgFile.toPath(), beforeSha);
			Path outputDir = createRclOutputDir(outputRoot);
			List<String> command = buildRclCommand(cfgFile, script, outputDir, modelId, priorStatus);
			appendStatusText("Assistente: revisão offline em pasta exclusiva: " + outputDir.toAbsolutePath()
					+ System.lineSeparator());
			if (priorStatus != null) {
				appendStatusText("Assistente: decisões anteriores do mesmo CFG e conteúdo serão consideradas."
						+ System.lineSeparator());
			}

			RclRunResult result = null;
			String errorText = null;
			try {
				result = executeCommand(command, assistantRoot, RCL_TIMEOUT_SECONDS);
			}
			catch (Exception ex) {
				errorText = ex.getClass().getSimpleName() + ": " + ex.getMessage();
			}

			String afterSha = null;
			try {
				afterSha = sha256File(cfgFile.toPath());
			}
			catch (IOException ex) {
				errorText = (errorText == null ? "" : errorText + "; ")
						+ "CFG não pôde ser conferido após a revisão";
			}
			boolean unchanged = beforeSha.equals(afterSha);
			Path reportFile = outputDir.resolve(modelId + "_offline_review.json");
			String reportError = validateOfflineRclReport(reportFile, cfgFile.toPath(), modelId, assistantRoot);
			boolean validReport = reportError == null;
			String reportSha = null;
			if (validReport) {
				try {
					reportSha = sha256File(reportFile);
				}
				catch (IOException ex) {
					validReport = false;
					reportError = "não foi possível calcular SHA-256 do JSON de revisão";
				}
			}
			boolean complete = result != null && result.finished && result.exitCode == 0
					&& unchanged && validReport;

			// The receipt is written even when Python fails or reaches the time limit.
			// A missing receipt is an error, never a successful review.
			writeRclReceipt(outputDir, cfgFile.toPath(), modelId, beforeSha, afterSha, reportSha,
					result, errorText, complete);

			StringBuilder sb = new StringBuilder();
			sb.append("Assistente: revisão ").append(complete ? "OFFLINE_CONCLUIDA" : "FALHOU_OU_BLOQUEADA")
					.append(System.lineSeparator());
			sb.append("Sessão: ").append(outputDir.getFileName()).append(System.lineSeparator());
			sb.append("Resultados: ").append(outputDir.toAbsolutePath()).append(System.lineSeparator());
			sb.append("CFG SHA-256 antes: ").append(beforeSha).append(System.lineSeparator());
			sb.append("CFG SHA-256 depois: ").append(afterSha == null ? "indisponível" : afterSha)
					.append(System.lineSeparator());
			if (!unchanged)
				sb.append("BLOQUEADO: CFG modificado ou não verificável. Não houve restauração automática.")
						.append(System.lineSeparator());
			if (!validReport)
				sb.append("BLOQUEADO: relatório JSON inválido ou de outro modelo: ")
						.append(reportError).append(System.lineSeparator());
			if (errorText != null)
				sb.append("Erro técnico: ").append(errorText).append(System.lineSeparator());
			if (result != null) {
				sb.append("Processo concluído=").append(result.finished)
						.append(", código=").append(result.exitCode).append(System.lineSeparator());
				if (!result.output.trim().isEmpty()) {
					sb.append("Saída da revisão:").append(System.lineSeparator());
					sb.append(limitOutput(result.output, MAX_PROCESS_OUTPUT_CHARS))
							.append(System.lineSeparator());
				}
			}
			appendStatusText(sb.toString());
		}
		catch (Exception ex) {
			appendStatusText("Erro na revisão local: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private void openRclOutputFolder() {
		try {
			JaamSimModel simModel = GUIFrame.getJaamSimModel();
			File anchorFile = new File(".");
			if (simModel != null && simModel.getConfigFile() != null)
				anchorFile = simModel.getConfigFile();

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir resultados: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			Path outputDir = getRclOutputRoot(assistantRoot);
			openFolder(outputDir, "Abrir histórico de revisões offline");
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao abrir resultados da revisão: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private void openBriefingOutputFolder() {
		if (openCompanionFolderIfAvailable())
			return;

		try {
			JaamSimModel simModel = GUIFrame.getJaamSimModel();
			File anchorFile = new File(".");
			if (simModel != null && simModel.getConfigFile() != null)
				anchorFile = simModel.getConfigFile();

			Path assistantRoot = findAssistantRoot(anchorFile);
			if (assistantRoot == null) {
				appendStatusText(System.lineSeparator()
						+ "Abrir briefing: raiz da extensao não encontrada. Configure JAAMSIM_ASSISTANT_ROOT." + System.lineSeparator());
				return;
			}

			openFolder(getBriefingOutputDir(assistantRoot), "Abrir briefing");
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao abrir briefing: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private boolean openCompanionFolderIfAvailable() {
		try {
			refreshCompanionBinding(false);
			if (activeCompanionZip == null) {
				appendChatMessage("Assistente",
						"O briefing ainda está em memória. Salve o modelo para criar o arquivo companheiro .jaamsim-ai.zip.");
				return true;
			}
			openFolder(activeCompanionZip.getParent(), "Abrir arquivo companheiro");
			return true;
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao abrir arquivo companheiro: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
			return true;
		}
	}

	/**
	 * Display local RCL history; read-only. The active CFG path selects the
	 * model, while its current hash distinguishes previous revisions.
	 * No Python, JaamSim batch, LLM or P004 action is dispatched.
	 */
	private void showReviewHistory() {
		try {
			JaamSimModel simModel = GUIFrame.getJaamSimModel();
			File cfgFile = simModel == null ? null : simModel.getConfigFile();
			File anchor = cfgFile == null ? new File(".") : cfgFile;
			Path assistantRoot = findAssistantRoot(anchor);
			if (assistantRoot == null) {
				appendStatusText("Histórico RCL: extensão acadêmica indisponível."
						+ System.lineSeparator());
				return;
			}
			Path root = getRclOutputRoot(assistantRoot);
			if (!Files.isDirectory(root)) {
				appendStatusText("Histórico RCL: ainda não há revisões registradas."
						+ System.lineSeparator());
				return;
			}

			Path selected = cfgFile == null ? null : cfgFile.toPath().toAbsolutePath().normalize();
			String currentHash = null;
			if (selected != null && Files.isRegularFile(selected)) {
				try {
					currentHash = sha256File(selected);
				}
				catch (IOException ex) {
					// History remains available, but no current-version match is claimed.
				}
			}

			ArrayList<Path> runs = new ArrayList<>();
			try (java.util.stream.Stream<Path> folders = Files.list(root)) {
				for (Path folder : (Iterable<Path>) folders::iterator) {
					if (Files.isDirectory(folder, LinkOption.NOFOLLOW_LINKS))
						runs.add(folder);
				}
			}
			Collections.sort(runs, (a, b) -> {
				try {
					return Files.getLastModifiedTime(b).compareTo(Files.getLastModifiedTime(a));
				}
				catch (IOException ex) {
					return a.toString().compareTo(b.toString());
				}
			});

			StringBuilder sb = new StringBuilder();
			sb.append("Histórico RCL — consulta local, sem executar nova revisão")
					.append(System.lineSeparator());
			if (selected != null) {
				sb.append("Modelo selecionado: ").append(selected).append(System.lineSeparator());
				if (currentHash == null)
					sb.append("Hash atual: indisponível (não confirma equivalência de versão)")
							.append(System.lineSeparator());
			}
			else {
				sb.append("Sem CFG ativo: exibindo as últimas revisões locais de todos os modelos.")
						.append(System.lineSeparator());
			}
			int shown = 0;
						for (Path run : runs) {
				Path receiptFile = run.resolve("JAAM_AI_OFFLINE_REVIEW_RECEIPT.json");
				if (!Files.isRegularFile(receiptFile, LinkOption.NOFOLLOW_LINKS))
					continue;
				try {
					JSONValue receipt = readJsonFile(receiptFile);
					if (!"jaam.ai.offline_review.receipt.v1".equals(
							getStringChild(receipt, "schema", "")))
						continue;
					String sourceRaw = getStringChild(receipt, "source_cfg", "");
					if (sourceRaw.isEmpty())
						continue;
					Path source = Paths.get(sourceRaw).toAbsolutePath().normalize();
					if (selected != null && !selected.equals(source)) {
						continue;
					}
					String sha = getStringChild(receipt, "cfg_sha256_after", "");
					boolean sameVersion = currentHash != null
							&& currentHash.equalsIgnoreCase(sha)
							&& Boolean.TRUE.equals(isTrueChild(receipt, "cfg_unchanged"));
					String runId = getStringChild(receipt, "run_id", run.getFileName().toString());
					String outcome = getStringChild(receipt, "outcome", "RESULTADO_DESCONHECIDO");
					String sourceLabel = "JAAMSIM_GUI_RCL".equals(
							getStringChild(receipt, "origin", "")) ? "janela JaamSim" : "CMD central/local";
					sb.append(System.lineSeparator());
					sb.append(shown + 1).append(". ").append(runId)
							.append(" | ").append(outcome)
							.append(" | ").append(sourceLabel).append(System.lineSeparator());
					sb.append("   CFG: ").append(source.getFileName()).append(System.lineSeparator());
					sb.append("   UTC: ").append(getStringChild(receipt, "utc_timestamp", "não informado"))
							.append(System.lineSeparator());
					if (selected != null) {
						sb.append("   Versão do CFG: ")
								.append(sameVersion ? "mesmo conteúdo atual" : "outra versão / não verificável")
								.append(System.lineSeparator());
					}
					sb.append("   Pasta: ").append(run.toAbsolutePath()).append(System.lineSeparator());
					shown++;
					if (shown >= 10)
						break;
				}
				catch (Exception ex) {
					// Corrupted receipts cannot be treated as reliable evidence.
				}
			}
			if (shown == 0)
				sb.append("Nenhum recibo compatível com o modelo selecionado.")
						.append(System.lineSeparator());
			sb.append(System.lineSeparator());
			sb.append("Recibos são registros locais, não assinaturas digitais.")
					.append(System.lineSeparator());
			sb.append("Decisões anteriores somente são usadas quando caminho, SHA-256 e estado coincidem.")
					.append(System.lineSeparator());
			appendStatusText(sb.toString());
		}
		catch (Exception ex) {
			appendStatusText("Histórico RCL: falha ao ler registros: "
					+ ex.getClass().getSimpleName() + ": " + ex.getMessage()
					+ System.lineSeparator());
		}
	}

	private static Boolean isTrueChild(JSONValue parent, String key) {
		JSONValue value = getMapChild(parent, key);
		return value == null ? null : value.isTrue();
	}

	private void showLatestSuggestions() {
		try {
			SuggestionFileContext context = findSuggestionFileContext();
			if (context == null)
				return;
		if (context.statusFile == null) {
			appendStatusText(System.lineSeparator()
					+ "Assistente: não encontrei arquivo *_suggestions_status.json em "
					+ context.outputDir.toAbsolutePath() + System.lineSeparator()
					+ "Peça para eu revisar o modelo primeiro." + System.lineSeparator());
			return;
		}

			setStatusText(buildSuggestionSummary(context.statusFile));
			statusArea.setCaretPosition(0);
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao mostrar sugestões: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private void updateFirstPendingSuggestion(String newStatus) {
		try {
			SuggestionFileContext context = findSuggestionFileContext();
			if (context == null)
				return;
			if (context.statusFile == null) {
				appendStatusText(System.lineSeparator()
						+ "Assistente: não encontrei arquivo de status. Peça uma revisão do modelo primeiro." + System.lineSeparator());
				return;
			}

			JSONValue root = readJsonFile(context.statusFile);
			JSONValue suggestions = getMapChild(root, "suggestions");
			if (suggestions == null || !suggestions.isList()) {
				appendStatusText(System.lineSeparator()
						+ "Assistente: o arquivo de status não contém lista de sugestões." + System.lineSeparator());
				return;
			}

			for (JSONValue suggestion : suggestions.listVal) {
				if (suggestion == null || !suggestion.isMap())
					continue;

				String currentStatus = getStringChild(suggestion, "status", "pending");
				if (!"pending".equals(currentStatus))
					continue;

				String suggestionId = getStringChild(suggestion, "suggestion_id", "(unknown)");
				String reason = "accepted".equals(newStatus)
						? "Aceita pelo operador no assistente nativo JaamSim; o modelo ainda deve ser editado manualmente."
						: "Rejeitada pelo operador no assistente nativo JaamSim; nenhuma alteração de modelo foi autorizada.";

				suggestion.mapVal.put("status", JSONValue.makeStringVal(newStatus));
				suggestion.mapVal.put("status_reason", JSONValue.makeStringVal(reason));
				suggestion.mapVal.put("status_actor", JSONValue.makeStringVal(System.getProperty("user.name", "operator")));
				suggestion.mapVal.put("status_updated_at", JSONValue.makeStringVal(OffsetDateTime.now().toString()));

				byte[] payload = (JSONWriter.writeJSONValue(root) + System.lineSeparator()).getBytes(StandardCharsets.UTF_8);
				Files.write(context.statusFile, payload);

				setStatusText(buildSuggestionSummary(context.statusFile));
				appendRichText(System.lineSeparator()
						+ "Decisão registrada para " + suggestionId + ": " + newStatus + System.lineSeparator()
						+ "Peça nova revisão para atualizar auditoria e plano de mudanças permitidas." + System.lineSeparator());
				statusArea.setCaretPosition(statusArea.getDocument().getLength());
				return;
			}

			appendStatusText(System.lineSeparator()
					+ "Assistente: não encontrei sugestão pendente." + System.lineSeparator());
		}
		catch (Exception ex) {
			appendStatusText(System.lineSeparator()
					+ "Erro ao registrar decisão: " + ex.getClass().getSimpleName()
					+ ": " + ex.getMessage() + System.lineSeparator());
		}
	}

	private SuggestionFileContext findSuggestionFileContext() throws IOException {
		JaamSimModel simModel = GUIFrame.getJaamSimModel();
		File anchorFile = simModel == null ? null : simModel.getConfigFile();
		if (anchorFile == null || !anchorFile.isFile()) {
			appendStatusText("Assistente: salve o CFG para recuperar decisões do modelo correto."
					+ System.lineSeparator());
			return null;
		}
		Path assistantRoot = findAssistantRoot(anchorFile);
		if (assistantRoot == null) {
			appendStatusText("Assistente: raiz da extensão não encontrada. Configure JAAMSIM_ASSISTANT_ROOT."
					+ System.lineSeparator());
			return null;
		}
		Path reportRoot = getRclOutputRoot(assistantRoot);
		Path status = findSuggestionStatusFile(reportRoot, anchorFile.toPath(),
				sha256File(anchorFile.toPath()));
		return new SuggestionFileContext(reportRoot, status);
	}

	private static Path getRclOutputRoot(Path assistantRoot) {
		return assistantRoot.resolve("output").resolve("offline-review");
	}

	private static Path createRclOutputDir(Path root) throws IOException {
		Files.createDirectories(root);
		String utc = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss_SSS")
				.withZone(ZoneOffset.UTC).format(java.time.Instant.now());
		return Files.createDirectory(root.resolve("gui_" + utc + "_"
				+ UUID.randomUUID().toString().replace("-", "").substring(0, 12)));
	}

	/**
	 * A status is reusable only for the exact source path and CFG content.
	 * The historical native_rcl flat folder has no authenticated provenance,
	 * so it is intentionally NOT imported to avoid cross-model decisions.
	 */
	private static Path findSuggestionStatusFile(Path reportRoot, Path cfgFile, String cfgSha)
			throws IOException {
		if (!Files.isDirectory(reportRoot))
			return null;
		Path source = cfgFile.toAbsolutePath().normalize();
		Path newest = null;
		FileTime newestTime = null;
		Path assistantRoot = reportRoot.getParent().getParent();
		try (java.util.stream.Stream<Path> runs = Files.list(reportRoot)) {
			for (Path run : (Iterable<Path>) runs::iterator) {
				if (!Files.isDirectory(run, LinkOption.NOFOLLOW_LINKS))
					continue;
				Path receiptFile = run.resolve("JAAM_AI_OFFLINE_REVIEW_RECEIPT.json");
				if (!Files.isRegularFile(receiptFile, LinkOption.NOFOLLOW_LINKS))
					continue;
				try {
					JSONValue receipt = readJsonFile(receiptFile);
					String recorded = getStringChild(receipt, "source_cfg", "");
					String recordedSha = getStringChild(receipt, "cfg_sha256_after", "");
					JSONValue unchanged = getMapChild(receipt, "cfg_unchanged");
					if (recorded.isEmpty() || !source.equals(Paths.get(recorded).toAbsolutePath().normalize())
							|| !cfgSha.equalsIgnoreCase(recordedSha)
							|| unchanged == null || !unchanged.isTrue())
						continue;

					String outcome = getStringChild(receipt, "outcome", "");
					if (!"COMPLETE_OFFLINE".equals(outcome) && !"COMPLETED_OFFLINE".equals(outcome))
						continue;

					// CMD reviews let the Python parser choose a normalized
					// model_id. The GUI may use a different explicit model_id.
					// Require ONE report in this run and read its actual ID,
					// rather than guessing a filename from the CFG name.
					Path candidateReport = findUniqueRclReport(run);
					if (candidateReport == null
							|| validateOfflineRclReport(candidateReport, cfgFile, null, assistantRoot) != null)
						continue;
					JSONValue report = readJsonFile(candidateReport);
					String actualModelId = getStringChild(getMapChild(report, "analysis"), "model_id", "");

					String pinnedReportSha = getStringChild(receipt, "report_sha256", "");
					String origin = getStringChild(receipt, "origin", "");
					if (pinnedReportSha.isEmpty()) {
						// Historical CMD receipts did not yet pin report hashes.
						// New GUI receipts must always pin them to be reusable.
						if ("JAAMSIM_GUI_RCL".equals(origin))
							continue;
					}
					else if (!pinnedReportSha.equalsIgnoreCase(sha256File(candidateReport)))
						continue;

					Path statusFile = run.resolve(actualModelId + "_suggestions_status.json");
					if (!Files.isRegularFile(statusFile, LinkOption.NOFOLLOW_LINKS))
						continue;
					JSONValue status = readJsonFile(statusFile);
					if (!actualModelId.equals(getStringChild(status, "model_id", "")))
						continue;
					Path statusSource = resolveReportedSource(
							getStringChild(status, "input_file", ""), assistantRoot);
					if (!source.equals(statusSource))
						continue;

					FileTime modified = Files.getLastModifiedTime(statusFile);
					if (newest == null || modified.compareTo(newestTime) > 0) {
						newest = statusFile;
						newestTime = modified;
					}
				}
				catch (Exception ex) {
					// Corrupt or partial histories cannot authorize decisions.
				}
			}
		}
		return newest;
	}

	/**
	 * Fail closed for runs with zero or multiple RCL reports. A run is a
	 * single-model review; ambiguity cannot select trusted suggestions.
	 */
	private static Path findUniqueRclReport(Path run) throws IOException {
		Path found = null;
		try (java.util.stream.Stream<Path> reports = Files.list(run)) {
			for (Path path : (Iterable<Path>) reports::iterator) {
				if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
						|| !path.getFileName().toString().endsWith("_offline_review.json"))
					continue;
				if (found != null)
					return null;
				found = path;
			}
		}
		return found;
	}

	/**
	 * Validate the RCL JSON rather than treating file existence as proof of
	 * a successful review. A forged or stale JSON for another CFG is not a
	 * successful result, even if the subprocess exits with code zero.
	 * Returns null on success or a user-readable reason for rejection.
	 */
	private static String validateOfflineRclReport(Path reportFile, Path cfgFile, String modelId,
			Path assistantRoot) {
		if (!Files.isRegularFile(reportFile, LinkOption.NOFOLLOW_LINKS))
			return "arquivo de revisão ausente";
		try {
			JSONValue report = readJsonFile(reportFile);
			if (report == null || !report.isMap())
				return "estrutura JSON inválida";
			if (!"offline_deterministico".equals(getStringChild(report, "mode", "")))
				return "revisão não é determinística offline";
			if (!"cfg".equals(getStringChild(report, "input_type", "")))
				return "relatório não foi gerado a partir de CFG";

			Path recorded = resolveReportedSource(getStringChild(report, "input_file", ""), assistantRoot);
			if (recorded == null || !cfgFile.toAbsolutePath().normalize().equals(recorded))
				return "origem do CFG não corresponde ao modelo selecionado";

			JSONValue analysis = getMapChild(report, "analysis");
			String actualModelId = getStringChild(analysis, "model_id", "");
			if (actualModelId.isEmpty() || actualModelId.equals(".") || actualModelId.equals("..")
					|| !actualModelId.matches("[A-Za-z0-9._-]+"))
				return "identificador do modelo inválido para arquivo local";
			if (modelId != null && !modelId.equals(actualModelId))
				return "identificador do modelo é diferente";
			if (!reportFile.getFileName().toString().equals(actualModelId + "_offline_review.json"))
				return "arquivo do relatório não corresponde ao identificador declarado";

			JSONValue usage = getMapChild(report, "ai_usage");
			if (!isFalseFlag(usage, "internet_api")
					|| !isFalseFlag(usage, "llm_online")
					|| !isFalseFlag(usage, "local_ai"))
				return "modo offline sem IA não foi comprovado";
			JSONValue llmAssist = getMapChild(report, "llm_online_assist");
			if (!isFalseFlag(llmAssist, "enabled"))
				return "relatório registra camada LLM habilitada";

			Path statusFile = reportFile.getParent().resolve(actualModelId + "_suggestions_status.json");
			if (!Files.isRegularFile(statusFile, LinkOption.NOFOLLOW_LINKS))
				return "arquivo de status da mesma revisão não encontrado";
			JSONValue statuses = readJsonFile(statusFile);
			if (!actualModelId.equals(getStringChild(statuses, "model_id", "")))
				return "arquivo de status pertence a outro modelo";
			Path statusSource = resolveReportedSource(getStringChild(statuses, "input_file", ""), assistantRoot);
			if (statusSource == null || !recorded.equals(statusSource))
				return "origem do arquivo de status não corresponde ao relatório";
			if (getMapChild(statuses, "suggestions") == null
					|| !getMapChild(statuses, "suggestions").isList())
				return "arquivo de status sem lista de sugestões";
			return null;
		}
		catch (Exception ex) {
			return "arquivo JSON não pôde ser validado: " + ex.getClass().getSimpleName();
		}
	}

	private static boolean isFalseFlag(JSONValue parent, String key) {
		JSONValue value = getMapChild(parent, key);
		return value != null && value.isFalse();
	}

	private static Path resolveReportedSource(String raw, Path assistantRoot) {
		if (raw == null || raw.trim().isEmpty())
			return null;
		Path recorded = Paths.get(raw);
		if (!recorded.isAbsolute()) {
			// modulo_ia_offline.display_path() relativizes to
			// snapshot_analyzer.ROOT == assistant_paths.ASSISTANT_ROOT.
			// The CMD and Java must resolve against this same directory.
			recorded = assistantRoot.resolve(recorded);
		}
		return recorded.toAbsolutePath().normalize();
	}

	private static String sha256File(Path file) throws IOException {
		MessageDigest md;
		try {
			md = MessageDigest.getInstance("SHA-256");
		}
		catch (NoSuchAlgorithmException ex) {
			throw new IOException("SHA-256 não disponível", ex);
		}
		try (java.io.InputStream in = Files.newInputStream(file)) {
			byte[] buf = new byte[32768];
			int count;
			while ((count = in.read(buf)) != -1)
				md.update(buf, 0, count);
		}
		StringBuilder hash = new StringBuilder();
		for (byte b : md.digest())
			hash.append(String.format(Locale.ROOT, "%02x", b & 0xff));
		return hash.toString();
	}

	private static void writeRclReceipt(Path outputDir, Path cfgFile, String modelId,
			String beforeSha, String afterSha, String reportSha,
			RclRunResult result, String error, boolean complete)
			throws IOException {
		JSONValue receipt = JSONValue.makeObject();
		receipt.mapVal.put("schema", JSONValue.makeStringVal("jaam.ai.offline_review.receipt.v1"));
		receipt.mapVal.put("run_id", JSONValue.makeStringVal(outputDir.getFileName().toString()));
		receipt.mapVal.put("utc_timestamp", JSONValue.makeStringVal(OffsetDateTime.now(ZoneOffset.UTC).toString()));
		receipt.mapVal.put("source_cfg", JSONValue.makeStringVal(cfgFile.toAbsolutePath().normalize().toString()));
		receipt.mapVal.put("model_id", JSONValue.makeStringVal(modelId));
		receipt.mapVal.put("cfg_sha256_before", JSONValue.makeStringVal(beforeSha));
		receipt.mapVal.put("cfg_sha256_after", afterSha == null
				? JSONValue.makeNullVal() : JSONValue.makeStringVal(afterSha));
		receipt.mapVal.put("cfg_unchanged", beforeSha.equals(afterSha)
				? JSONValue.makeTrueVal() : JSONValue.makeFalseVal());
		receipt.mapVal.put("report_sha256", reportSha == null
				? JSONValue.makeNullVal() : JSONValue.makeStringVal(reportSha));
		receipt.mapVal.put("exit_code", JSONValue.makeNumVal(result == null ? -1 : result.exitCode));
		receipt.mapVal.put("outcome", JSONValue.makeStringVal(complete ? "COMPLETE_OFFLINE" : "FAILED_OR_BLOCKED"));
		receipt.mapVal.put("finished", result != null && result.finished
				? JSONValue.makeTrueVal() : JSONValue.makeFalseVal());
		receipt.mapVal.put("output_directory", JSONValue.makeStringVal(outputDir.toAbsolutePath().toString()));
		receipt.mapVal.put("origin", JSONValue.makeStringVal("JAAMSIM_GUI_RCL"));
		receipt.mapVal.put("error", error == null ? JSONValue.makeNullVal() : JSONValue.makeStringVal(error));
		receipt.mapVal.put("automatic_model_changes", JSONValue.makeFalseVal());
		receipt.mapVal.put("external_llm_invoked", JSONValue.makeFalseVal());
		receipt.mapVal.put("p004_inference_authorized", JSONValue.makeFalseVal());
		receipt.mapVal.put("full45_authorized", JSONValue.makeFalseVal());
		Path target = outputDir.resolve("JAAM_AI_OFFLINE_REVIEW_RECEIPT.json");
		Path temporary = outputDir.resolve("JAAM_AI_OFFLINE_REVIEW_RECEIPT.json.tmp");
		Files.write(temporary, (JSONWriter.writeJSONValue(receipt) + System.lineSeparator())
				.getBytes(StandardCharsets.UTF_8));
		Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
	}

	private static String buildSuggestionSummary(Path statusFile) throws Exception {
		JSONValue root = readJsonFile(statusFile);
		JSONValue suggestions = getMapChild(root, "suggestions");

		StringBuilder sb = new StringBuilder();
		sb.append("Sugestões e decisões - visão nativa").append(System.lineSeparator());
		sb.append("Arquivo de status: ").append(statusFile.toAbsolutePath()).append(System.lineSeparator());
		sb.append("Guardrail: decisões atualizam apenas o status da sugestão; objetos do modelo não são editados.")
				.append(System.lineSeparator());
		sb.append(System.lineSeparator());

		if (suggestions == null || !suggestions.isList()) {
			sb.append("Não encontrei lista de sugestões no arquivo de status.").append(System.lineSeparator());
			return sb.toString();
		}

		int pending = 0;
		int accepted = 0;
		int rejected = 0;
		int shown = 0;
		for (JSONValue suggestion : suggestions.listVal) {
			if (suggestion == null || !suggestion.isMap())
				continue;

			String status = getStringChild(suggestion, "status", "pending");
			if ("pending".equals(status))
				pending++;
			else if ("accepted".equals(status))
				accepted++;
			else if ("rejected".equals(status))
				rejected++;

			if (shown >= 8)
				continue;
			shown++;
			sb.append(shown).append(". ");
			sb.append(getStringChild(suggestion, "suggestion_id", "(id)"));
			sb.append(" [").append(status).append("] ");
			sb.append(getStringChild(suggestion, "rule_id", "(rule)"));
			sb.append(" / ").append(getStringChild(suggestion, "component_id", "(component)"));
			sb.append(System.lineSeparator());
			sb.append("   Título: ").append(getStringChild(suggestion, "title", "(sem título)")).append(System.lineSeparator());
			sb.append("   Sugestão: ").append(getStringChild(suggestion, "suggested_change", "(sem sugestão)"))
					.append(System.lineSeparator());
		}

		sb.append(System.lineSeparator());
		sb.append("Contagem: pendentes=").append(pending)
				.append(", aceitas=").append(accepted)
				.append(", rejeitadas=").append(rejected)
				.append(", total=").append(suggestions.listVal.size())
				.append(System.lineSeparator());
		sb.append("Escreva 'aceitar sugestão' ou 'rejeitar sugestão' para registrar decisão na primeira pendente. Depois peça nova revisão.")
				.append(System.lineSeparator());
		return sb.toString();
	}

	private String buildBriefingChatSummary(Path briefingJson, Path outputDir, boolean usedOnlineAi, String caseId)
			throws Exception {
		JSONValue root = readJsonFile(briefingJson);
		JSONValue briefing = getMapChild(root, "briefing");
		if (briefing == null || !briefing.isMap())
			return "Assistente: gerei os arquivos do briefing, mas não consegui resumir o JSON automaticamente."
					+ System.lineSeparator()
					+ "Assistente: escreva 'abrir briefing' para abrir a pasta dos documentos."
					+ System.lineSeparator();

		JSONValue prd = getMapChild(briefing, "prd_interno");
		String objective = getStringChild(prd, "objetivo",
				"Organizar a ideia em um modelo de simulação pequeno, verificável e evolutivo.");
		rememberBriefingQuestions(briefing, outputDir, caseId);

		StringBuilder sb = new StringBuilder();
		sb.append(System.lineSeparator());
		sb.append("Assistente: pronto. Montei uma primeira versão do briefing da simulação.").append(System.lineSeparator());
		sb.append(System.lineSeparator());
		sb.append("Objetivo preliminar: ").append(objective).append(System.lineSeparator());
		appendStringList(sb, prd, "entidades_provaveis", "Elementos provaveis do modelo", 3);
		appendStringList(sb, prd, "metricas", "Métricas iniciais", 3);

		sb.append(System.lineSeparator());
		if (activeCompanionZip != null) {
			sb.append("Registrei a história, o PRD interno, épicos/stories e auditoria no arquivo companheiro ")
					.append(activeCompanionZip.getFileName())
					.append(". Se quiser localizar o pacote, escreva 'abrir briefing'.")
					.append(System.lineSeparator());
		}
		else {
			sb.append("Mantive a história, o PRD interno, épicos/stories e auditoria em memória. ")
					.append("Salve o modelo para criar o arquivo companheiro .jaamsim-ai.zip.")
					.append(System.lineSeparator());
		}
		if (hasPendingBriefingQuestion()) {
			sb.append("Vamos continuar refinando. ")
					.append(pendingBriefingQuestions.get(0)).append(System.lineSeparator());
		}
		else {
			sb.append("Próximo passo: me diga uma restrição importante do modelo, ou peça 'revisar modelo' depois de montar o fluxo inicial.").append(System.lineSeparator());
		}
		return sb.toString();
	}

	private void rememberBriefingQuestions(JSONValue briefing, Path outputDir, String caseId) {
		activeBriefingOutputDir = outputDir;
		activeBriefingCaseId = caseId;
		pendingBriefingQuestions.clear();
		briefingAnswers.clear();
		pendingBriefingQuestions.addAll(getStringListChild(briefing, "perguntas_ao_operador", 6));
	}

	private static void appendPracticalNextSteps(StringBuilder sb) {
		sb.append(System.lineSeparator());
		sb.append("Dicas para construir no JaamSim:").append(System.lineSeparator());
		sb.append("- Comece pelo fluxo mínimo: chegada -> fila/estoque -> processo -> saída.").append(System.lineSeparator());
		sb.append("- Transforme frases como '1 produto por minuto' em tempo de processo ou taxa registrada no modelo.").append(System.lineSeparator());
		sb.append("- Use o StatFit quando tiver amostras de tempos reais; se não tiver, registre a hipótese usada.").append(System.lineSeparator());
		sb.append("- Rode primeiro um cenário pequeno, confira se as entidades fluem, depois compare alternativas.").append(System.lineSeparator());
	}

	private static String buildBriefingFailureSummary(RclRunResult result) {
		StringBuilder sb = new StringBuilder();
		sb.append(System.lineSeparator());
		sb.append("Assistente: tentei gerar o briefing, mas não consegui concluir com segurança.")
				.append(System.lineSeparator());
		sb.append("Status técnico: finalizado=").append(result.finished)
				.append(", código=").append(result.exitCode)
				.append(System.lineSeparator());
		if (!result.finished) {
			sb.append("O processo passou do tempo limite de ").append(RCL_TIMEOUT_SECONDS)
					.append(" segundos.").append(System.lineSeparator());
		}
		if (!result.output.trim().isEmpty()) {
		sb.append("Resumo técnico para diagnóstico:").append(System.lineSeparator());
			sb.append(limitOutput(result.output, 1600)).append(System.lineSeparator());
		}
		sb.append("Você pode tentar novamente com uma ideia menor ou verificar se o Python está funcionando.")
				.append(System.lineSeparator());
		return sb.toString();
	}

	private static void appendStringList(StringBuilder sb, JSONValue parent, String key, String label, int limit) {
		JSONValue list = getMapChild(parent, key);
		if (list == null || !list.isList() || list.listVal.isEmpty())
			return;

		sb.append(label).append(":").append(System.lineSeparator());
		int count = 0;
		for (JSONValue item : list.listVal) {
			if (item == null || !item.isString())
				continue;
			sb.append("- ").append(item.stringVal).append(System.lineSeparator());
			count++;
			if (count >= limit)
				break;
		}
	}

	private static ArrayList<String> getStringListChild(JSONValue parent, String key, int limit) {
		ArrayList<String> values = new ArrayList<>();
		JSONValue list = getMapChild(parent, key);
		if (list == null || !list.isList() || list.listVal.isEmpty())
			return values;

		for (JSONValue item : list.listVal) {
			if (item == null || !item.isString())
				continue;
			values.add(item.stringVal);
			if (values.size() >= limit)
				break;
		}
		return values;
	}

	private static JSONValue readJsonFile(Path file) throws Exception {
		return JSONParser.parse(new String(Files.readAllBytes(file), StandardCharsets.UTF_8));
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

	private static boolean getBooleanChild(JSONValue parent, String key, boolean fallback) {
		JSONValue value = getMapChild(parent, key);
		if (value == null)
			return fallback;
		if (value.isTrue())
			return true;
		if (value.isFalse())
			return false;
		return fallback;
	}

	private void appendStatusText(final String text) {
		final String cleanText = cleanDisplayText(text);
		SwingUtilities.invokeLater(() -> {
			appendRichText(cleanText);
			scrollChatToEnd();
		});
	}

	private void setStatusText(final String text) {
		statusArea.setText("");
		appendRichText(cleanDisplayText(text));
		scrollChatToEnd();
	}

	private void appendRichText(final String text) {
		StyledDocument document = statusArea.getStyledDocument();
		SimpleAttributeSet plain = new SimpleAttributeSet();
		StyleConstants.setFontFamily(plain, Font.SANS_SERIF);
		StyleConstants.setFontSize(plain, 13);
		SimpleAttributeSet bold = new SimpleAttributeSet(plain);
		StyleConstants.setBold(bold, true);

		String value = text == null ? "" : text;
		int cursor = 0;
		boolean boldMode = false;
		try {
			while (cursor < value.length()) {
				int marker = value.indexOf("**", cursor);
				if (marker < 0) {
					document.insertString(document.getLength(), value.substring(cursor), boldMode ? bold : plain);
					break;
				}
				if (marker > cursor)
					document.insertString(document.getLength(), value.substring(cursor, marker), boldMode ? bold : plain);
				boldMode = !boldMode;
				cursor = marker + 2;
			}
		}
		catch (BadLocationException ex) {
			statusArea.setText(statusArea.getText() + value.replace("**", ""));
		}
	}

	private static String cleanDisplayText(String text) {
		if (text == null || text.isEmpty())
			return "";

		String normalized = normalizeUtf8Text(text)
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
			String line = lines[i].trim().replaceAll("[ ]{3,}", "  ");
			sb.append(repairBrokenAccentSpacing(line));
		}
		return sb.toString();
	}

	private static String normalizeUtf8Text(String text) {
		return Normalizer.normalize(repairCommonMojibake(text), Normalizer.Form.NFC);
	}

	private static String repairCommonMojibake(String text) {
		String repaired = text;
		repaired = repaired.replace("Ã¡", "á").replace("Ã ", "à").replace("Ã¢", "â").replace("Ã£", "ã");
		repaired = repaired.replace("Ã©", "é").replace("Ãª", "ê");
		repaired = repaired.replace("Ã­", "í");
		repaired = repaired.replace("Ã³", "ó").replace("Ã´", "ô").replace("Ãµ", "õ");
		repaired = repaired.replace("Ãº", "ú").replace("Ã¼", "ü");
		repaired = repaired.replace("Ã§", "ç");
		repaired = repaired.replace("Ã�", "Á").replace("Ã‰", "É").replace("Ã“", "Ó");
		repaired = repaired.replace("Ã‡", "Ç");
		repaired = repaired.replace("â€“", "–").replace("â€”", "—").replace("â€™", "'").replace("â€œ", "\"").replace("â€", "\"");
		return repaired;
	}

	private static String repairBrokenAccentSpacing(String line) {
		if (line == null || line.isEmpty())
			return "";

		String repaired = line;
		repaired = repaired.replaceAll("(?iu)\\bl\\s+ó\\s+gic([ao]s?)\\b", "lógic$1");
		repaired = repaired.replaceAll("(?iu)\\bmanh\\s+ã\\b", "manhã");
		repaired = repaired.replaceAll("(?iu)\\bmaç\\s+ã\\b", "maçã");
		repaired = repaired.replaceAll("(?iu)\\b(\\p{L}*[áéíóúâêôãõç]\\p{L}*)\\s+(ão|ões|o|a|os|as|rio|ria|rios|rias|dia|dio|nimo|ximo|xima|nico|nica|veis|vel|gios|gio|tica|tico|metros?|gicos?|gicas?|mente|stic[ao]s?)\\b", "$1$2");
		repaired = repaired.replaceAll("(?iu)\\b(inter|time|pré|pre|pós|pos|auto|semi|sub|multi|não|nao|fim)-\\s+(\\p{L})", "$1-$2");
		return repaired;
	}

	private static String repairTypographyArtifacts(String line) {
		if (line == null || line.isEmpty())
			return "";
		String repaired = repairPortugueseAccentSpacing(line);
		repaired = repaired.replaceAll("(?iu)\\b(inter|time|pré|pre|pós|pos|auto|semi|sub|multi|não|nao)-\\s+([\\p{L}])", "$1-$2");
		repaired = repaired.replaceAll("(?iu)\\bservi\\s+ç\\s*o\\b", "serviço");
		repaired = repaired.replaceAll("(?iu)\\bdistribui\\s+ç\\s*ã\\s*o\\b", "distribuição");
		repaired = repaired.replaceAll("(?iu)\\bconfigura\\s+ç\\s*ã\\s*o\\b", "configuração");
		return repaired;
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
		repaired = repaired.replaceAll("(?iu)\\bVoc\u00EA(?=(gostaria|poderia|pode|quer|tem|deve|vai|consegue|prefere|informou)\\b)", "Você ");
		repaired = repaired.replaceAll("(?iu)\\bvoc\u00EA(?=(gostaria|poderia|pode|quer|tem|deve|vai|consegue|prefere|informou)\\b)", "você ");
		repaired = repaired.replaceAll("(?iu)\\bJ\u00E1(?=(temos|o|a|come\u00E7a|comecei)\\b)", "Já ");
		repaired = repaired.replaceAll("(?iu)\\b(tempo|processo|taxa|agenda|fluxo)-\\s+([\\p{L}])", "$1-$2");
		return repaired;
	}

	private static String repairAsciiPortugueseWords(String line) {
		if (line == null || line.isEmpty())
			return "";
		String repaired = line;
		repaired = repaired.replaceAll("(?iu)\\bVoce\\b", "Você");
		repaired = repaired.replaceAll("(?iu)\\bvoce\\b", "você");
		repaired = repaired.replaceAll("(?iu)\\bsimulacao\\b", "simulação");
		repaired = repaired.replaceAll("(?iu)\\bsimulacoes\\b", "simulações");
		repaired = repaired.replaceAll("(?iu)\\bconstrucao\\b", "construção");
		repaired = repaired.replaceAll("(?iu)\\bdistribuicao\\b", "distribuição");
		repaired = repaired.replaceAll("(?iu)\\bdistribuicoes\\b", "distribuições");
		repaired = repaired.replaceAll("(?iu)\\bconfiguracao\\b", "configuração");
		repaired = repaired.replaceAll("(?iu)\\bconfiguracoes\\b", "configurações");
		repaired = repaired.replaceAll("(?iu)\\bnotificacao\\b", "notificação");
		repaired = repaired.replaceAll("(?iu)\\bnotificacoes\\b", "notificações");
		repaired = repaired.replaceAll("(?iu)\\bautocorrecao\\b", "autocorreção");
		repaired = repaired.replaceAll("(?iu)\\bsugestao\\b", "sugestão");
		repaired = repaired.replaceAll("(?iu)\\bsugestoes\\b", "sugestões");
		repaired = repaired.replaceAll("(?iu)\\brevisao\\b", "revisão");
		repaired = repaired.replaceAll("(?iu)\\bdecisao\\b", "decisão");
		repaired = repaired.replaceAll("(?iu)\\bsaida\\b", "saída");
		repaired = repaired.replaceAll("(?iu)\\bsaidas\\b", "saídas");
		repaired = repaired.replaceAll("(?iu)\\bmetricas\\b", "métricas");
		repaired = repaired.replaceAll("(?iu)\\bhistorica\\b", "histórica");
		repaired = repaired.replaceAll("(?iu)\\bhipotese\\b", "hipótese");
		repaired = repaired.replaceAll("(?iu)\\bcenarios\\b", "cenários");
		repaired = repaired.replaceAll("(?iu)\\baleatorias\\b", "aleatórias");
		repaired = repaired.replaceAll("(?iu)\\bopcao\\b", "opção");
		repaired = repaired.replaceAll("(?iu)\\bdeterministico\\b", "determinístico");
		repaired = repaired.replaceAll("(?iu)\\breposicao\\b", "reposição");
		repaired = repaired.replaceAll("(?iu)\\bminimo\\b", "mínimo");
		repaired = repaired.replaceAll("(?iu)\\bmaximo\\b", "máximo");
		repaired = repaired.replaceAll("(?iu)\\bhorario\\b", "horário");
		repaired = repaired.replaceAll("(?iu)\\bmanha\\b", "manhã");
		repaired = repaired.replaceAll("(?iu)\\boleo\\b", "óleo");
		repaired = repaired.replaceAll("(?iu)\\bservico\\b", "serviço");
		repaired = repaired.replaceAll("(?iu)\\bdiarias\\b", "diárias");
		repaired = repaired.replaceAll("(?iu)\\butil\\b", "útil");
		repaired = repaired.replaceAll("(?iu)\\buteis\\b", "úteis");
		repaired = repaired.replaceAll("(?iu)\\bja\\b", "já");
		repaired = repaired.replaceAll("(?iu)\\bnao\\b", "não");
		repaired = repaired.replaceAll("(?iu)\\bacoes\\b", "ações");
		repaired = repaired.replaceAll("(?iu)\\ba\u00E7oes\\b", "ações");
		return repaired;
	}

	private void configureSmoothWheelScroll() {
		MouseWheelListener listener = event -> {
			if (smoothScrollCheckBox == null || !smoothScrollCheckBox.isSelected())
				return;
			stopChatScrollTimer();
			JScrollBar bar = chatScrollPane.getVerticalScrollBar();
			int bottom = getScrollBottom(bar);
			int base = smoothWheelTarget >= 0 ? smoothWheelTarget : bar.getValue();
			int unit = Math.max(10, bar.getUnitIncrement());
			int delta = event.getUnitsToScroll() * unit;
			if (delta == 0)
				return;
			smoothWheelTarget = clamp(base + delta, 0, bottom);
			event.consume();
			startSmoothScrollTo(smoothWheelTarget, false, false);
		};
		chatScrollPane.addMouseWheelListener(listener);
		chatScrollPane.getViewport().addMouseWheelListener(listener);
		statusArea.addMouseWheelListener(listener);
	}

	private void scrollChatToEnd() {
		if (chatScrollPane == null) {
			statusArea.setCaretPosition(statusArea.getDocument().getLength());
			return;
		}
		JScrollBar bar = chatScrollPane.getVerticalScrollBar();
		if (smoothScrollCheckBox == null || !smoothScrollCheckBox.isSelected()) {
			stopChatScrollTimer();
			statusArea.setCaretPosition(statusArea.getDocument().getLength());
			bar.setValue(getScrollBottom(bar));
			return;
		}

		SwingUtilities.invokeLater(() -> SwingUtilities.invokeLater(() -> {
			smoothWheelTarget = -1;
			startSmoothScrollTo(getScrollBottom(bar), true, true);
		}));
	}

	private void startSmoothScrollTo(int target, boolean followEnd, boolean updateCaretWhenDone) {
		if (chatScrollPane == null)
			return;
		JScrollBar bar = chatScrollPane.getVerticalScrollBar();
		stopChatScrollTimer();
		chatScrollTimer = new Timer(10, null);
		chatScrollTimer.addActionListener(event -> {
			int liveTarget = followEnd ? getScrollBottom(bar) : clamp(target, 0, getScrollBottom(bar));
			int current = bar.getValue();
			int delta = liveTarget - current;
			if (Math.abs(delta) <= 2) {
				bar.setValue(liveTarget);
				if (updateCaretWhenDone)
					statusArea.setCaretPosition(statusArea.getDocument().getLength());
				stopChatScrollTimer();
				return;
			}
			int step = Math.max(4, Math.abs(delta) / 4);
			bar.setValue(current + (delta > 0 ? step : -step));
		});
		chatScrollTimer.setRepeats(true);
		chatScrollTimer.start();
	}

	private void stopChatScrollTimer() {
		if (chatScrollTimer != null) {
			chatScrollTimer.stop();
			chatScrollTimer = null;
		}
	}

	private static int getScrollBottom(JScrollBar bar) {
		return Math.max(0, bar.getMaximum() - bar.getVisibleAmount());
	}

	private static int clamp(int value, int minimum, int maximum) {
		return Math.max(minimum, Math.min(maximum, value));
	}

	private static ArrayList<Entity> collectUserEntities(JaamSimModel simModel) {
		ArrayList<Entity> entities = new ArrayList<>();
		for (Entity ent : simModel.getClonesOfIterator(Entity.class)) {
			if (!isUserVisibleEntity(ent))
				continue;

			entities.add(ent);
		}
		return entities;
	}

	private static boolean isUserVisibleEntity(Entity ent) {
		if (ent == null || ent.isDead() || !ent.isRegistered() || ent.isPreDefined())
			return false;

		if (ent instanceof ObjectType)
			return false;

		String packageName = ent.getClass().getPackage().getName();
		if (packageName.startsWith("com.jaamsim.units"))
			return false;
		if (packageName.startsWith("com.jaamsim.DisplayModels"))
			return false;
		if (packageName.startsWith("com.jaamsim.BasicObjects"))
			return false;

		return true;
	}

	private static Map<String, Integer> countObjectTypes(List<Entity> entities) {
		TreeMap<String, Integer> counts = new TreeMap<>();
		for (Entity ent : entities) {
			ObjectType type = ent.getObjectType();
			String typeName = type == null ? ent.getClass().getSimpleName() : type.getName();
			addCount(counts, typeName);
		}
		return counts;
	}

	private static Map<String, Integer> countClasses(List<Entity> entities) {
		TreeMap<String, Integer> counts = new TreeMap<>();
		for (Entity ent : entities) {
			addCount(counts, ent.getClass().getSimpleName());
		}
		return counts;
	}

	private static void addCount(Map<String, Integer> counts, String key) {
		Integer current = counts.get(key);
		counts.put(key, current == null ? 1 : current + 1);
	}

	private static int countReferences(List<Entity> entities) {
		int total = 0;
		for (Entity ent : entities) {
			total += ent.getEntityReferences().size();
		}
		return total;
	}

	private static int countEditableInputs(List<Entity> entities) {
		int total = 0;
		for (Entity ent : entities) {
			total += ent.getEditableInputs().size();
		}
		return total;
	}

	private static void appendTypeSummary(StringBuilder sb, Map<String, Integer> typeCounts) {
		sb.append("Object type summary:").append(System.lineSeparator());
		if (typeCounts.isEmpty()) {
			sb.append("- no user-visible objects detected").append(System.lineSeparator());
			sb.append(System.lineSeparator());
			return;
		}

		for (Map.Entry<String, Integer> entry : topEntries(typeCounts, 12)) {
			sb.append("- ").append(entry.getKey()).append(": ").append(entry.getValue()).append(System.lineSeparator());
		}
		sb.append(System.lineSeparator());
	}

	private static void appendProcessFlowSummary(StringBuilder sb, Map<String, Integer> classCounts) {
		sb.append("Process-flow landmarks:").append(System.lineSeparator());
		appendLandmark(sb, classCounts, "EntityGenerator");
		appendLandmark(sb, classCounts, "EntityGen");
		appendLandmark(sb, classCounts, "Queue");
		appendLandmark(sb, classCounts, "Server");
		appendLandmark(sb, classCounts, "EntityProcessor");
		appendLandmark(sb, classCounts, "EntitySink");
		appendLandmark(sb, classCounts, "Resource");
		appendLandmark(sb, classCounts, "Statistics");
		sb.append(System.lineSeparator());
	}

	private static void appendLandmark(StringBuilder sb, Map<String, Integer> classCounts, String className) {
		Integer count = classCounts.get(className);
		sb.append("- ").append(className).append(": ").append(count == null ? 0 : count).append(System.lineSeparator());
	}

	private static void appendEntitySamples(StringBuilder sb, List<Entity> entities) {
		sb.append("First entities scanned:").append(System.lineSeparator());
		if (entities.isEmpty()) {
			sb.append("- none").append(System.lineSeparator());
			sb.append(System.lineSeparator());
			return;
		}

		int limit = Math.min(entities.size(), 10);
		for (int i = 0; i < limit; i++) {
			Entity ent = entities.get(i);
			sb.append("- ").append(ent.getName()).append(" [").append(ent.getClass().getSimpleName()).append("]");
			sb.append(System.lineSeparator());
		}
		sb.append(System.lineSeparator());
	}

	private static void appendNativePrecheck(StringBuilder sb, Map<String, Integer> classCounts, int referenceCount) {
		sb.append("Native precheck:").append(System.lineSeparator());
		if (getCount(classCounts, "Queue") > 0 && getCount(classCounts, "Server") == 0
				&& getCount(classCounts, "EntityProcessor") == 0) {
			sb.append("- review suggested: queues exist but no Server/EntityProcessor was detected.").append(System.lineSeparator());
		}
		if (getCount(classCounts, "EntityGenerator") == 0 && getCount(classCounts, "EntityGen") == 0) {
			sb.append("- review suggested: no entity generator was detected.").append(System.lineSeparator());
		}
		if (getCount(classCounts, "EntitySink") == 0) {
			sb.append("- review suggested: no entity sink was detected.").append(System.lineSeparator());
		}
		if (referenceCount == 0) {
			sb.append("- review suggested: no entity references were found in scanned inputs.").append(System.lineSeparator());
		}
		sb.append("- these checks are exploratory; use Run Local RCL for the offline rule engine.").append(System.lineSeparator());
		sb.append(System.lineSeparator());
	}

	private static int getCount(Map<String, Integer> counts, String key) {
		Integer count = counts.get(key);
		return count == null ? 0 : count;
	}

	private static List<Map.Entry<String, Integer>> topEntries(Map<String, Integer> counts, int limit) {
		ArrayList<Map.Entry<String, Integer>> entries = new ArrayList<>(counts.entrySet());
		Collections.sort(entries, (a, b) -> {
			int countCompare = b.getValue().compareTo(a.getValue());
			if (countCompare != 0)
				return countCompare;
			return a.getKey().compareTo(b.getKey());
		});
		return entries.subList(0, Math.min(entries.size(), limit));
	}

	private static Path findAssistantRoot(File cfgFile) {
		// An explicitly configured extension is authoritative. If missing,
		// never silently execute another Python module found near the CFG or
		// in the JVM working directory. This applies equally to GUI and StatFit.
		// The original CMD verifies the native package before setting this
		// environment root. Do not let -Djaamsim.assistant.root supersede it.
		String configuredRoot = AssistantLaunchSettings.preferLauncherEnvironment(
				System.getenv("JAAMSIM_ASSISTANT_ROOT"),
				System.getProperty("jaamsim.assistant.root"));
		if (configuredRoot != null)
			return resolveAssistantRootCandidate(Paths.get(configuredRoot), "modulo_ia_offline.py");

		// Legacy discovery is allowed only when neither source configured a root.
		ArrayList<Path> candidates = new ArrayList<>();
		Path currentDir = Paths.get("").toAbsolutePath();
		candidates.add(currentDir);

		Path cursor = cfgFile.toPath().toAbsolutePath().getParent();
		while (cursor != null) {
			candidates.add(cursor);
			cursor = cursor.getParent();
		}

		for (Path candidate : candidates) {
			Path resolved = resolveAssistantRootCandidate(candidate, "modulo_ia_offline.py");
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

	private static List<String> buildRclCommand(File cfgFile, Path script, Path outputDir, String modelId, Path statusFile) {
		ArrayList<String> command = new ArrayList<>();
		command.add(resolvePythonCommand());
		command.add(script.toString());
		command.add(cfgFile.getAbsolutePath());
		command.add("--input-type");
		command.add("cfg");
		command.add("--output-dir");
		command.add(outputDir.toString());
		command.add("--model-id");
		command.add(modelId);
		command.add("--case-id");
		command.add("NATIVE");
		command.add("--variant");
		command.add("jaamsim-gui");
		command.add("--profile");
		command.add("beginner");
		if (statusFile != null && Files.isRegularFile(statusFile)) {
			command.add("--status-file");
			command.add(statusFile.toString());
			// The file hash alone does not freeze suggestion ordering across RCL versions.
			command.add("--strict-status-identity");
		}
		return command;
	}

	private static List<String> buildBriefingCommand(Path script, Path outputDir, String caseId, String idea,
			boolean useOnlineAi) {
		ArrayList<String> command = new ArrayList<>();
		command.add(resolvePythonCommand());
		command.add(script.toString());
		command.add("--idea");
		command.add(idea);
		command.add("--case-id");
		command.add(caseId);
		command.add("--output-dir");
		command.add(outputDir.toString());
		if (useOnlineAi)
			command.add("--online");
		return command;
	}

	private static List<String> buildChatCommand(Path script, Path outputDir, Path historyFile, String caseId,
			String message, String modelContext) {
		ArrayList<String> command = new ArrayList<>();
		command.add(resolvePythonCommand());
		command.add(script.toString());
		command.add("--message");
		command.add(message);
		command.add("--history-file");
		command.add(historyFile.toString());
		command.add("--output-dir");
		command.add(outputDir.toString());
		command.add("--case-id");
		command.add(caseId);
		command.add("--model-context");
		command.add(modelContext);
		command.add("--max-tokens");
		command.add(Integer.toString(CHAT_MAX_TOKENS));
		command.add("--require-online");
		return command;
	}

	private static Path getBriefingOutputDir(Path assistantRoot) {
		return assistantRoot.resolve("output")
				.resolve("briefing")
				.resolve("native_conversation");
	}

	private static Path getChatOutputDir(Path assistantRoot) {
		return assistantRoot.resolve("output")
				.resolve("briefing")
				.resolve("native_chat");
	}

	private static String buildBriefingCaseId(File anchorFile, String idea) {
		String base = null;
		if (anchorFile != null && anchorFile.isFile())
			base = buildModelId(anchorFile);
		if (base == null || base.trim().isEmpty())
			base = idea;

		base = base.toLowerCase().replaceAll("[^a-z0-9._-]+", "_");
		base = base.replaceAll("_+", "_").replaceAll("^_+|_+$", "");
		if (base.length() > 48)
			base = base.substring(0, 48);
		if (base.isEmpty())
			base = "simulation";
		return "native_" + base + "_briefing";
	}

	private static String resolvePythonCommand() {
		// Same trust boundary as the configured assistant root. In a CMD
		// launch, JAAMSIM_PYTHON is the interpreter validated on option 8.
		String configured = AssistantLaunchSettings.preferLauncherEnvironment(
				System.getenv("JAAMSIM_PYTHON"),
				System.getProperty("jaamsim.python"));
		return configured == null ? "python" : configured;
	}

	private static String buildModelId(File cfgFile) {
		String name = cfgFile.getName();
		int dot = name.lastIndexOf('.');
		if (dot > 0)
			name = name.substring(0, dot);
		name = name.replaceAll("[^A-Za-z0-9._-]+", "_");
		if (name.isEmpty())
			name = "jaamsim_model";
		return name;
	}

	private static RclRunResult executeCommand(List<String> command, Path workingDir, int timeoutSeconds)
			throws IOException, InterruptedException {
		ProcessBuilder builder = new ProcessBuilder(command);
		builder.directory(workingDir.toFile());
		builder.redirectErrorStream(true);
		builder.environment().put("PYTHONIOENCODING", "utf-8");
		builder.environment().put("PYTHONUTF8", "1");

		Process process = builder.start();
		StringBuilder output = new StringBuilder();
		Thread outputThread = new Thread(() -> readProcessOutput(process, output), "JaamSim AI Assistant RCL Output");
		outputThread.setDaemon(true);
		outputThread.start();

		boolean finished = process.waitFor(timeoutSeconds, TimeUnit.SECONDS);
		if (!finished)
			process.destroyForcibly();

		outputThread.join(3000);
		int exitCode = finished ? process.exitValue() : -1;
		return new RclRunResult(finished, exitCode, output.toString());
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

	private static final class ConversationTurn {

		private final String timestamp;
		private final String role;
		private final String speaker;
		private final String content;

		private ConversationTurn(String timestamp, String role, String speaker, String content) {
			this.timestamp = timestamp == null ? "" : timestamp;
			this.role = role == null ? "assistant" : role;
			this.speaker = speaker == null ? "Assistente" : speaker;
			this.content = content == null ? "" : content;
		}

		private String toJsonLine() {
			return "{\"timestamp\":\"" + jsonEscape(timestamp)
					+ "\",\"role\":\"" + jsonEscape(role)
					+ "\",\"speaker\":\"" + jsonEscape(speaker)
					+ "\",\"content\":\"" + jsonEscape(content)
					+ "\"}";
		}
	}

	private static final class AttachmentRecord {

		private final String originalName;
		private final String storedName;
		private final String storedPath;
		private final String kind;
		private final long sizeBytes;
		private final String addedAt;

		private AttachmentRecord(String originalName, String storedName, String storedPath,
				String kind, long sizeBytes, String addedAt) {
			this.originalName = originalName == null ? "attachment" : originalName;
			this.storedName = storedName == null ? sanitizeFileName(this.originalName) : storedName;
			this.storedPath = storedPath == null ? "" : storedPath;
			this.kind = kind == null ? "arquivo" : kind;
			this.sizeBytes = sizeBytes;
			this.addedAt = addedAt == null ? "" : addedAt;
		}
	}

	private static final class RclRunResult {

		private final boolean finished;
		private final int exitCode;
		private final String output;

		private RclRunResult(boolean finished, int exitCode, String output) {
			this.finished = finished;
			this.exitCode = exitCode;
			this.output = output;
		}
	}

	private static final class SuggestionFileContext {

		private final Path outputDir;
		private final Path statusFile;

		private SuggestionFileContext(Path outputDir, Path statusFile) {
			this.outputDir = outputDir;
			this.statusFile = statusFile;
		}
	}
}
