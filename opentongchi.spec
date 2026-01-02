# https://fedoraproject.org/wiki/How_to_create_an_RPM_package
# Built and maintained by John Boero - boeroboy@gmail.com
# In honor of Seth Vidal https://www.redhat.com/it/blog/thank-you-seth-vidal
# Completed with help from Athropic Claude Opus v4.5

%global pypi_name opentongchi
%global app_name OpenTongchi
%global github_owner jboero
%global github_repo opentongchi

Name:           opentongchi
Version:        0.2.0
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

# Install icon (multiple sizes for better scaling)
for size in 256 128 64 48; do
    install -D -m 644 img/opentongchi.webp \
        %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/%{name}.webp
done

# Also install to pixmaps for legacy support
install -D -m 644 img/opentongchi.webp %{buildroot}%{_datadir}/pixmaps/%{name}.webp

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
%{_datadir}/icons/hicolor/*/apps/%{name}.webp
%{_datadir}/pixmaps/%{name}.webp
%config(noreplace) %{_sysconfdir}/xdg/autostart/%{name}.desktop

%changelog
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
