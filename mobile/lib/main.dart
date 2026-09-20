/// Karrierekrake mobile companion — Flutter entrypoint.
///
/// HARD RULE: This application is a NEW Flutter codebase under `mobile/`.
/// It must NOT wrap, embed, transpile, or port the Windows/PySide desktop app.
/// Shared contracts live in `contracts/` at the repo root.
library;

import 'package:flutter/material.dart';
import 'package:karrierekrake_mobile/app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const KarrierekrakeMobileApp());
}
