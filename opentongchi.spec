%global pypi_name opentongchi
%global app_name OpenTongchi
%global github_owner jboero
%global github_repo opentongchi

Name:           opentongchi
Version:        1.4.2
Release:        1%{?dist}
Summary:        System Tray Manager for Open Source Infrastructure Tools

License:        MPL-2.0
URL:            https://github.com/%{github_owner}/%{github_repo}
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
BuildRequires:  desktop-file-utils

Requires:       python3 >= 3.10
Requires:       python3-pyside6
Requires:       python3-keyring
Requires:       hicolor-icon-theme

# Optional runtime dependencies for full functionality
Recommends:     terraform
Recommends:     packer
Recommends:     boundary

%description
OpenTongchi is a Qt6-based system tray application for managing open source
infrastructure tools including OpenBao (Vault), Consul, Nomad, Boundary,
OpenTofu (Terraform), and Packer.

Features:
- Browse and manage secrets, KV stores, and policies via nested tree menus
- Monitor job status, services, and nodes with color-coded status indicators
- Execute Terraform/OpenTofu plans and applies as background processes
- Connect to Boundary targets directly from the system tray
- Build Packer images with log browsing
- Automatic token and lease renewal in the background
- Native table-based CRUD dialogs for JSON documents

%prep
%autosetup -n %{github_repo}-%{version}

%build
%{python3} setup.py build

%install
# Install Python package manually (avoiding deprecated macros)
mkdir -p %{buildroot}%{python3_sitelib}/%{pypi_name}
cp -r app %{buildroot}%{python3_sitelib}/%{pypi_name}/
cp main.py %{buildroot}%{python3_sitelib}/%{pypi_name}/
touch %{buildroot}%{python3_sitelib}/%{pypi_name}/__init__.py

# Create wrapper script
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/%{name} << 'WRAPPER'
#!/usr/bin/env python3
import sys
import os

# Add module path
sys.path.insert(0, '%{python3_sitelib}/%{pypi_name}')
os.chdir('%{python3_sitelib}/%{pypi_name}')

from main import main
main()
WRAPPER
chmod 755 %{buildroot}%{_bindir}/%{name}

# Also install to pixmaps for legacy support
install -D -m 644 img/opentongchi.png %{buildroot}%{_datadir}/pixmaps/opentongchi.png

# Install desktop file
mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/%{name}.desktop << 'DESKTOP'
[Desktop Entry]
Name=%{app_name}
GenericName=Infrastructure Manager
Comment=System Tray Manager for Open Source Infrastructure Tools
Exec=%{name}
Icon=%{name}
Terminal=false
Type=Application
Categories=Development;System;Utility;Network;
Keywords=vault;consul;nomad;terraform;opentofu;packer;boundary;openbao;infrastructure;devops;hashicorp;
StartupNotify=false
StartupWMClass=%{name}
X-GNOME-UsesNotifications=true
DESKTOP

desktop-file-validate %{buildroot}%{_datadir}/applications/%{name}.desktop

# Install autostart entry (disabled by default - users can enable)
mkdir -p %{buildroot}%{_sysconfdir}/xdg/autostart
cat > %{buildroot}%{_sysconfdir}/xdg/autostart/%{name}.desktop << 'AUTOSTART'
[Desktop Entry]
Name=%{app_name}
GenericName=Infrastructure Manager
Comment=System Tray Manager for Open Source Infrastructure Tools
Exec=%{name}
Icon=%{name}
Terminal=false
Type=Application
Categories=Development;System;Utility;Network;
X-GNOME-Autostart-enabled=false
Hidden=true
AUTOSTART

%check
# Basic syntax check
%{python3} -m py_compile %{buildroot}%{python3_sitelib}/%{pypi_name}/main.py
%{python3} -m py_compile %{buildroot}%{python3_sitelib}/%{pypi_name}/app/*.py
%{python3} -m py_compile %{buildroot}%{python3_sitelib}/%{pypi_name}/app/clients/*.py
%{python3} -m py_compile %{buildroot}%{python3_sitelib}/%{pypi_name}/app/menus/*.py

%post
/bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null || :

%postun
if [ $1 -eq 0 ] ; then
    /bin/touch --no-create %{_datadir}/icons/hicolor &>/dev/null
    /usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
fi

%posttrans
/usr/bin/gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :

%files
%license LICENSE
%doc README.md
%{_bindir}/%{name}
%{python3_sitelib}/%{pypi_name}/
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png
%{_datadir}/pixmaps/%{name}.png
%config(noreplace) %{_sysconfdir}/xdg/autostart/%{name}.desktop

%changelog
* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.3.1-1
- Added HCL syntax highlighting for Nomad job templates
- Added JSON syntax highlighting for Consul service templates
- Dark theme editor with One Dark color scheme
- Highlights: keywords, blocks, strings, numbers, comments, interpolation

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.4.2-1
- Added Mandarin name (汤匙) to About dialog

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.4.1-1
- Improved sound playback - now uses command-line players first (paplay, pw-play, aplay)
- Added PipeWire support (pw-play)
- Falls back to Qt QMediaPlayer for better format support
- Eliminates noisy Qt multimedia debug messages

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.4.0-1
- Added sound notifications for process completion and errors
- New SoundManager class with system sound discovery
- Sound settings in Global tab: enable/disable, success sound, error sound
- Test buttons to preview sounds in settings dialog
- Supports system theme sounds, custom paths, or disabled
- Falls back to paplay/aplay/afplay if QtMultimedia unavailable

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.3.0-1
- Boundary: Simplified Sessions menu (removed redundant "All Sessions")
- Consul: Added "New Service..." with 7 comprehensive JSON templates
- Nomad: Enhanced "New Job..." with 8 HCL templates for all job types
- Templates include extensive comments documenting all attributes
- Added TemplateSelectionDialog for template-based resource creation
- Nomad: Added job_parse endpoint for HCL to JSON conversion

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.3.2-1
- JSON syntax highlighting applied to all Raw JSON view tabs
- About dialog now shows dynamic version number
- Fixed syntax highlighter assignment bug for unsupported syntax types

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.2.1-1
- Fixed NoneType errors when lists are empty (Groups, Sessions, etc.)
- Added "New..." menu options for creating Organizations, Projects, Users, Groups, Roles, Aliases
- Added create/delete methods to Boundary client
- Empty menus now show "(No items yet)" with New option

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.2.0-1
- Boundary menu restructured to match web UI
- Added Orgs tree navigation
- Added Aliases menu with target alias listing
- Added Workers menu with worker status and details
- Added Global IAM menu (Users, Groups, Roles, Auth Methods)
- Connection processes now registered with global process manager
- Boundary connections can be stopped from the Processes menu

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.1.3-1
- Fixed Users & Groups menu - now properly shows Users, Groups, Roles submenus
- Each submenu loads data from global scope and shows details on click

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.1.2-1
- Fixed client caching issue - client now refreshes on each menu build
- Improved auth error messages to show which credentials ARE configured
- Debug info helps identify settings issues

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.1.1-1
- Fixed password authentication flow for Boundary
- Auth now happens automatically when credentials are configured
- CLI commands now properly wait for authentication before executing
- Added auth error display in status menu with retry option
- Improved token extraction from Boundary auth response

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.1.0-1
- Boundary menu rebuilt with org/scope tree navigation
- Organizations menu showing global → orgs → projects hierarchy
- Fixed token passing via BOUNDARY_TOKEN environment variable
- All Targets and All Sessions now work correctly with authentication
- Added per-project views: targets, sessions, host catalogs, credential stores
- Added per-org views: users, groups, roles
- Auth methods menu at global scope

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 1.0.0-1
- Secure secret storage using system keyring
- Tokens and passwords stored in KDE Wallet / GNOME Keyring / macOS Keychain
- Automatic migration of secrets from QSettings to keyring
- Added keyring dependency

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.9.0-1
- Boundary username/password authentication support
- Auto-authentication when token not provided
- Added login_name, password, scope_id settings
- Environment variables: BOUNDARY_LOGIN_NAME, BOUNDARY_PASSWORD, BOUNDARY_SCOPE_ID
- Settings dialog updated with password auth fields
- Additional Boundary API methods (accounts, users, groups, roles)

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.8.0-1
- Comprehensive auth method configuration and management
- Userpass auth: full user CRUD, password changes
- AppRole auth: role CRUD, Role ID, Secret ID generation
- Token auth: token role management
- LDAP auth: config view, group and user management
- OIDC/JWT auth: config and role viewing
- Kubernetes auth: config and role viewing
- Auth method tuning (TTL, description, token type)
- Disable auth method with confirmation

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.7.0-1
- Policy editor now uses large text box for HCL editing
- Added Namespace management (Enterprise feature)
- Namespace switching and nested namespace support
- OpenTongchi title now clickable for About dialog
- Removed separate About menu item

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.6.0-1
- Identity management: Entities, Entity Aliases, Groups, Group Aliases
- Full CRUD for all Identity objects
- Entity alias management per entity
- Group membership management
- Lookup entity/group by name, ID, or alias
- Merge entities functionality

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.5.0-1
- Generic secrets engine CRUD support for any engine type
- File upload/save support for Transit encrypt/decrypt/sign/verify/HMAC
- Database engine support with credential generation
- AWS engine support with IAM and STS credential generation
- SSH engine support with key signing
- TOTP engine support with code generation
- Cubbyhole personal secrets support
- Raw API read/write/list/delete for advanced users

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.4.0-1
- Enhanced OpenBao secrets management
- Full Transit engine support: create/delete keys, encrypt/decrypt, sign/verify, HMAC, rewrap
- Full PKI engine support: CA management, roles, issue/sign/revoke certificates
- Transit key rotation and export
- PKI root and intermediate CA generation
- Certificate listing and revocation
- Added missing refresh_client methods for OpenTofu and Packer

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.3.0-1
- Added comprehensive HCP Terraform Cloud support
- Organization info and settings management
- Variable Sets with full CRUD operations
- Workspace variables management
- Teams listing
- State versions browsing
- Lock/unlock workspaces
- Create/delete workspaces
- Destroy runs support

* Thu Jan 02 2025 John Boero <jboero@gmail.com> - 0.2.0-1
- Initial package release
- Support for OpenBao (Vault) secrets and auth management
- Support for Consul services and KV store
- Support for Nomad jobs, allocations, and nodes with status monitoring
- Support for Boundary targets and sessions
- Support for OpenTofu/Terraform local and HCP workspaces
- Support for Packer template builds
- Background process management with notifications
- Automatic token renewal
- Settings persistence via Qt settings
