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
 */
package com.jaamsim.ui;

/**
 * Shared precedence rule for the native AI assistant and StatFit.
 *
 * The original Windows launcher pins SHA-256 for JAAM_AI_NATIVE and sets
 * JAAMSIM_ASSISTANT_ROOT and JAAMSIM_PYTHON before starting Java. When
 * present, these inherited environment values are authoritative: a Java
 * -D override must not redirect either tool to an unpinned module or Python.
 *
 * In standalone launches where no environment setting exists, retain
 * backward-compatible -D property selection and Python PATH fallback.
 */
final class AssistantLaunchSettings {

	private AssistantLaunchSettings() {}

	static String preferLauncherEnvironment(String environmentValue, String propertyValue) {
		if (environmentValue != null && !environmentValue.trim().isEmpty())
			return environmentValue.trim();
		if (propertyValue != null && !propertyValue.trim().isEmpty())
			return propertyValue.trim();
		return null;
	}
}
