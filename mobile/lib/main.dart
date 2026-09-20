/// Karrierekrake mobile companion MVP — Flutter entrypoint.
///
/// HARD RULE: NEW Flutter codebase under `mobile/`.
/// Do NOT wrap/embed/port the Windows/PySide desktop app.
/// Local Drift persistence only — sync transport UNSPECIFIED.
library;

import 'package:flutter/material.dart';
import 'package:karrierekrake_mobile/app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const KarrierekrakeMobileApp());
}
