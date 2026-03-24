# OpenTongchi

<p align="center">
  <img src="img/opentongchi.png" alt="OpenTongchi Logo" width="128" height="128">
</p>

<p align="center">
  <strong>System Tray Manager for Open Source Infrastructure Tools</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#usage">Usage</a> •
  <a href="#supported-tools">Supported Tools</a> •
  <a href="#license">License</a>
</p>

---

OpenTongchi is a Qt6-based system tray widget that provides unified access to open source infrastructure tools. Browse secrets, monitor services, manage jobs, and execute infrastructure operations—all from your system tray.

## Features

### 🎯 Core Capabilities

- **Nested Tree Menus** — Browse secrets, services, jobs, and resources through intuitive hierarchical menus
- **Status Indicators** — Color-coded status emojis (🟢 healthy, 🔴 error, 🟡 pending, ⚪ unknown) at a glance
- **Table-Based CRUD** — Native key-value table editors for secrets and JSON documents with Tree/Table/Raw JSON views
- **Background Processes** — Execute long-running operations (plan, apply, build) with progress tracking
- **Automatic Renewal** — Configurable background token and lease renewal
- **System Notifications** — Desktop notifications for process completion, failures, and status changes

### 🔐 OpenBao (Vault)

- Browse and manage secrets engines (KV v1/v2, Transit, PKI, Database, AWS, SSH)
- Full CRUD operations on secrets with hidden value toggle
- Auth methods management
- Policy viewing and editing
- System operations (health, seal status, leader)
- Tools: wrap/unwrap, random generation, hashing
- Token management (lookup, renew, create)
- OpenAPI schema parsing for dynamic endpoint discovery

### 🔍 Consul

- Service catalog with health status indicators
- KV store browsing with nested folder support
- Node listing and details
- Health checks by state (passing, warning, critical)
- ACL tokens and policies
- Session management

### 📦 Nomad

- Job listing with status colors
- Job actions: stop, restart, dispatch, scale
- Allocation monitoring
- Node management with drain control
- Deployment tracking
- Namespace support
- Variable management
- **Automatic status monitoring** with configurable refresh interval
- Alerts on job failures and status changes

### 🚪 Boundary

- Target listing with connection status (🔒/🔓)
- One-click connect/disconnect
- Session management
- Scope browsing
- Active connection tracking

### 🏗️ OpenTofu / Terraform

- **Local Workspaces** (in `TOFU_HOME` directory)
  - Initialize, Plan, Apply, Destroy operations
  - Output viewing
  - Log history browsing
- **HCP Terraform (Terraform Cloud)**
  - Organization and workspace browsing
  - Run management (start, apply, discard)
  - Workspace locking/unlocking
  - Variable management

### 📦 Packer

- Template browsing from `PACKER_HOME` directory
- Initialize, Validate, Format operations
- Build execution as background process
- Build log history

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/jboero/opentongchi.git
cd opentongchi

# Install dependencies
pip install PySide6

# Run
python main.py
```

### Fedora / RHEL / CentOS (COPR)

```bash
# Enable the COPR repository
sudo dnf copr enable jboero/opentongchi

# Install
sudo dnf install opentongchi
```

### Manual Package Build

```bash
# Build SRPM
rpmbuild -bs opentongchi.spec

# Build RPM from SRPM
rpmbuild --rebuild opentongchi-0.1.0-1.src.rpm
```

## Configuration

### Environment Variables

OpenTongchi respects standard environment variables for each tool:

| Tool | Variables |
|------|-----------|
| **OpenBao/Vault** | `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_NAMESPACE`, `VAULT_SKIP_VERIFY` |
| **Consul** | `CONSUL_HTTP_ADDR`, `CONSUL_HTTP_TOKEN`, `CONSUL_NAMESPACE`, `CONSUL_DATACENTER` |
| **Nomad** | `NOMAD_ADDR`, `NOMAD_TOKEN`, `NOMAD_NAMESPACE`, `NOMAD_REGION` |
| **Boundary** | `BOUNDARY_ADDR`, `BOUNDARY_TOKEN` |
| **OpenTofu** | `TOFU_HOME` (default: `~/opentofu`), `TFE_TOKEN`, `TFE_ORG` |
| **Packer** | `PACKER_HOME` (default: `~/packer`) |
| **Global** | `HASHICORP_NAMESPACE` (applies to all products supporting namespaces) |

### Settings Dialog

Click **⚙️ Settings** in the tray menu to configure:

- Global namespace (applies across products)
- Notification preferences
- Per-product connection settings
- Token renewal intervals
- Refresh intervals

Settings are persisted using Qt's QSettings and survive restarts.

## Usage

### Starting the Application

```bash
# With environment variables
export VAULT_ADDR="http://localhost:8200"
export NOMAD_ADDR="http://localhost:4646"
opentongchi

# Or configure via Settings dialog after starting
opentongchi
```

### Menu Navigation

- **Left-click** or **Right-click** the tray icon to open the menu
- Hover over submenus to expand them (items load on first hover)
- **Wait cursor** indicates data is being fetched
- Use **🔄 Refresh** options to reload data

### Status Indicators

| Emoji | Meaning |
|-------|---------|
| 🟢 | Healthy / Running / Active / Passing |
| 🔴 | Error / Failed / Critical / Dead |
| 🟡 | Pending / Starting |
| 🟠 | Warning |
| ⚪ | Unknown / Stopped |
| 🔒 | Locked |
| 🔓 | Unlocked / Connected |

### Background Processes

Long-running operations appear in **⚡ Processes** menu:
- View running processes with elapsed time
- Cancel individual or all processes
- See recent completed/failed processes

## Architecture

```
opentongchi/
├── main.py                 # Application entry point
├── app/
│   ├── settings.py         # Configuration management
│   ├── process_manager.py  # Background task handling
│   ├── async_menu.py       # Lazy-loading menu widgets
│   ├── dialogs.py          # CRUD dialogs and settings
│   ├── systray.py          # Main system tray application
│   ├── clients/            # API clients (direct HTTP, no HVAC)
│   │   ├── base.py         # Base HTTP client
│   │   ├── openbao.py      # OpenBao/Vault client
│   │   ├── consul.py       # Consul client
│   │   ├── nomad.py        # Nomad client
│   │   ├── boundary.py     # Boundary CLI wrapper
│   │   ├── opentofu.py     # OpenTofu + HCP client
│   │   └── packer.py       # Packer client
│   └── menus/              # Menu builders for each product
│       ├── openbao.py
│       ├── consul.py
│       ├── nomad.py
│       ├── boundary.py
│       ├── opentofu.py
│       └── packer.py
└── img/
    └── opentongchi.png     # Application icon
```

## Dependencies

- **Python** 3.10+
- **PySide6** (Qt6 for Python)

Optional CLI tools (for full functionality):
- `tofu` or `terraform`
- `packer`
- `boundary`

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the **Mozilla Public License 2.0 (MPL-2.0)**.

See [LICENSE](LICENSE) for details.

## Acknowledgments

- Built with [Qt for Python (PySide6)](https://www.qt.io/qt-for-python)
- Inspired by the need for a unified interface to manage infrastructure tools
- Thanks to the open source community behind OpenBao, OpenTofu, and the HashiCorp ecosystem

---

<p align="center">
  Made with ❤️ for the infrastructure community
</p>
