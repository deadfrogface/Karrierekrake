import 'envelope.dart';

class ProfileDto {
  const ProfileDto({
    required this.envelope,
    this.firstName = '',
    this.lastName = '',
    this.street = '',
    this.postalCode = '',
    this.city = '',
    this.country = '',
    this.email = '',
    this.phone = '',
    this.languages = '',
    this.salaryExpectation = '',
    this.remotePreference = '',
    this.cvPath = '',
  });

  final ContractEnvelope envelope;
  final String firstName;
  final String lastName;
  final String street;
  final String postalCode;
  final String city;
  final String country;
  final String email;
  final String phone;
  final String languages;
  final String salaryExpectation;
  final String remotePreference;
  final String cvPath;

  static const schemaId = 'karrierekrake.profile';

  String get displayName {
    final n = '${firstName.trim()} ${lastName.trim()}'.trim();
    return n.isEmpty ? 'Profil' : n;
  }

  factory ProfileDto.fromJson(Map<String, dynamic> json) {
    return ProfileDto(
      envelope: ContractEnvelope.fromJson(json),
      firstName: readString(json, 'first_name'),
      lastName: readString(json, 'last_name'),
      street: readString(json, 'street'),
      postalCode: readString(json, 'postal_code'),
      city: readString(json, 'city'),
      country: readString(json, 'country'),
      email: readString(json, 'email'),
      phone: readString(json, 'phone'),
      languages: readString(json, 'languages'),
      salaryExpectation: readString(json, 'salary_expectation'),
      remotePreference: readString(json, 'remote_preference'),
      cvPath: readString(json, 'cv_path'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'first_name': firstName,
        'last_name': lastName,
        'street': street,
        'postal_code': postalCode,
        'city': city,
        'country': country,
        'email': email,
        'phone': phone,
        'languages': languages,
        'salary_expectation': salaryExpectation,
        'remote_preference': remotePreference,
        'cv_path': cvPath,
      };

  ProfileDto copyWith({
    String? firstName,
    String? lastName,
    String? street,
    String? postalCode,
    String? city,
    String? country,
    String? email,
    String? phone,
    String? languages,
    String? salaryExpectation,
    String? remotePreference,
  }) {
    return ProfileDto(
      envelope: envelope,
      firstName: firstName ?? this.firstName,
      lastName: lastName ?? this.lastName,
      street: street ?? this.street,
      postalCode: postalCode ?? this.postalCode,
      city: city ?? this.city,
      country: country ?? this.country,
      email: email ?? this.email,
      phone: phone ?? this.phone,
      languages: languages ?? this.languages,
      salaryExpectation: salaryExpectation ?? this.salaryExpectation,
      remotePreference: remotePreference ?? this.remotePreference,
      cvPath: cvPath,
    );
  }
}
