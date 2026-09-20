import 'package:flutter/material.dart';

import '../../contracts/profile_dto.dart';
import '../widgets/state_views.dart';
import 'shell.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, required this.profile});

  final ProfileDto? profile;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final TextEditingController _first;
  late final TextEditingController _last;
  late final TextEditingController _email;
  late final TextEditingController _city;
  late final TextEditingController _phone;

  @override
  void initState() {
    super.initState();
    final p = widget.profile;
    _first = TextEditingController(text: p?.firstName ?? '');
    _last = TextEditingController(text: p?.lastName ?? '');
    _email = TextEditingController(text: p?.email ?? '');
    _city = TextEditingController(text: p?.city ?? '');
    _phone = TextEditingController(text: p?.phone ?? '');
  }

  @override
  void dispose() {
    _first.dispose();
    _last.dispose();
    _email.dispose();
    _city.dispose();
    _phone.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.profile;
    if (p == null) {
      return const EmptyStateView(
        title: 'Kein Profil',
        message: 'Profil-Contract lokal laden oder light editing starten.',
        icon: Icons.person_off_outlined,
      );
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Profil (Light Edit)', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text(
          'PII bleibt geräte-lokal. cv_path ist opaque/nicht portabel. Kein Sync.',
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _first,
          decoration: const InputDecoration(labelText: 'Vorname'),
          textInputAction: TextInputAction.next,
        ),
        TextField(
          controller: _last,
          decoration: const InputDecoration(labelText: 'Nachname'),
          textInputAction: TextInputAction.next,
        ),
        TextField(
          controller: _email,
          decoration: const InputDecoration(labelText: 'E-Mail'),
          keyboardType: TextInputType.emailAddress,
        ),
        TextField(
          controller: _phone,
          decoration: const InputDecoration(labelText: 'Telefon'),
          keyboardType: TextInputType.phone,
        ),
        TextField(
          controller: _city,
          decoration: const InputDecoration(labelText: 'Stadt'),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: () async {
            final next = p.copyWith(
              firstName: _first.text,
              lastName: _last.text,
              email: _email.text,
              phone: _phone.text,
              city: _city.text,
            );
            await CompanionScope.of(context).repo.saveProfile(next);
            if (!context.mounted) return;
            await CompanionScope.of(context).refresh();
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Profil lokal gespeichert')),
              );
            }
          },
          child: const Text('Lokal speichern'),
        ),
      ],
    );
  }
}
