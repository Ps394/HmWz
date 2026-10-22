from hmwz.modules.registration.repositories import (
    MemberRegistrationRepository,
    RegistrationMessageRepository,
    RegistrationRoleRepository,
    RegistrationSettingsRepository,
)


class QSRegistrationSettingsRepository(RegistrationSettingsRepository):
    table_name = "QsRegistration"


class QSRegistrationRoleRepository(RegistrationRoleRepository):
    table_name = "QsRoles"
    settings_table_name = "QsRegistration"


class QSMemberRegistrationRepository(MemberRegistrationRepository):
    table_name = "QsRegistrations"
    settings_table_name = "QsRegistration"


class QSRegistrationMessageRepository(RegistrationMessageRepository):
    table_name = "QsList"


__all__ = [
    "QSMemberRegistrationRepository",
    "QSRegistrationMessageRepository",
    "QSRegistrationRoleRepository",
    "QSRegistrationSettingsRepository",
]
