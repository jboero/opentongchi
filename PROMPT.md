OpenTongchi v1.4.2 - Complete Summary
Project Overview
OpenTongchi (汤匙) is a Qt6/PySide6 system tray application for managing open source infrastructure tools. Licensed under MPL-2.0, hosted at https://github.com/jboero/opentongchi
Architecture
opentongchi/
├── main.py                 # Entry point with singleton lock
├── setup.py, requirements.txt, opentongchi.spec, LICENSE, README.md
├── img/opentongchi.svg     # Application icon
└── app/
    ├── __init__.py         # Version: 1.4.2
    ├── settings.py         # Configuration with env var support + keyring secrets + sound settings
    ├── process_manager.py  # Background tasks, token renewal, SoundManager
    ├── async_menu.py       # Lazy-loading menu widgets
    ├── dialogs.py          # CRUD dialogs, template dialogs, syntax highlighting, settings dialog
    ├── systray.py          # Main system tray application
    ├── clients/            # API clients (pure urllib, no HVAC)
    │   ├── base.py, openbao.py, consul.py, nomad.py, boundary.py, opentofu.py, packer.py
    └── menus/              # Menu builders for each product
        ├── openbao.py, consul.py, nomad.py, boundary.py, opentofu.py, packer.py
Key Features
Application Behavior

Singleton - Only one instance runs at a time (file lock in $XDG_RUNTIME_DIR)
Left-click - Opens Settings dialog
Right-click - Shows context menu
Settings dialog - Modal, prevents duplicates

Sound Notifications

Configurable in Settings → Global tab
Success/error sounds on process completion
Uses system sounds (Freedesktop, Yaru, GNOME, KDE) or custom paths
Plays via paplay, pw-play, aplay, or Qt fallback
Disabled by default

Syntax Highlighting

HCL - Keywords, blocks, strings, heredocs, comments, interpolation
JSON - Keys, strings, numbers, booleans
Applied to: Template dialogs, Policy editor, Raw JSON view tabs
Auto-detects light/dark mode

Template Dialogs

Nomad: 8 job templates (Service Docker/Exec, Batch, System, Parameterized, Java, Raw Exec, Connect Sidecar)
Consul: 7 service templates (Basic, Multiple Checks, gRPC, Weights, Connect Proxy, TTL, Sidecar)
Error handling: Dialog stays open on submission errors so user can fix and retry

Products Supported
ProductFeaturesOpenBao/VaultKV v1/v2, Transit, PKI, Database, AWS, SSH, TOTP, Cubbyhole, Auth Methods, Identity, Policies, Namespaces, System toolsConsulServices (with templates), KV Store, Nodes, Health, ACL, SessionsNomadJobs (with HCL templates), Allocations, Nodes, Deployments, Namespaces, VariablesBoundaryOrgs/Projects tree, Targets, Sessions, Host Catalogs, Credential Stores, Users/Groups/Roles, Aliases, Workers, Global IAMOpenTofuHCP Terraform Cloud workspaces, runs, statePackerBuild management
Environment Variables
ToolVariablesOpenBao/VaultVAULT_ADDR, VAULT_TOKEN, VAULT_NAMESPACE, VAULT_SKIP_VERIFYConsulCONSUL_HTTP_ADDR, CONSUL_HTTP_TOKEN, CONSUL_NAMESPACENomadNOMAD_ADDR, NOMAD_TOKEN, NOMAD_NAMESPACE, NOMAD_REGIONBoundaryBOUNDARY_ADDR, BOUNDARY_TOKEN, BOUNDARY_AUTH_METHOD_ID, BOUNDARY_LOGIN_NAME, BOUNDARY_PASSWORD, BOUNDARY_SCOPE_IDOpenTofuTOFU_HOME, TFE_TOKEN, TFE_ORGPackerPACKER_HOME
Secure Storage
Secrets stored in system keyring (KDE Wallet, GNOME Keyring, macOS Keychain):

openbao: token
consul: token
nomad: token
boundary: token, password
opentofu: hcp_token


Recreation Prompt
Create OpenTongchi (汤匙) - a Qt6/PySide6 system tray application for managing open source infrastructure tools (OpenBao/Vault, Consul, Nomad, Boundary, OpenTofu, Packer). Version 1.4.2, licensed MPL-2.0.

## Core Requirements

### Application Structure
- main.py: Entry point with singleton enforcement using file lock in $XDG_RUNTIME_DIR/opentongchi.lock. Exit silently (exit 0) if another instance is running.
- app/__init__.py: Contains __version__ = "1.4.2"
- app/settings.py: Dataclasses for each product's settings. Environment variable support. QSettings persistence. Secrets stored in system keyring via `keyring` library. GlobalSettings includes: namespace, theme, show_notifications, log_level, cache_dir, sounds_enabled (default False), sound_success ("system"), sound_error ("system").
- app/process_manager.py: ProcessManager for background QThread tasks with signals (process_finished, process_failed). TokenRenewalManager for auto-renewing OpenBao tokens. SoundManager for notification sounds - discovers system sounds from /usr/share/sounds/*, plays via paplay/pw-play/aplay CLI tools (preferred) or Qt QMediaPlayer fallback.
- app/systray.py: OpenTongchiTray class. Left-click opens Settings dialog. Right-click shows context menu (handled by Qt setContextMenu). Settings dialog must be modal and singleton (only one instance). About dialog shows "OpenTongchi (汤匙)" with dynamic version.
- app/async_menu.py: AsyncMenu widget for lazy-loading menu content with wait cursor.
- app/dialogs.py: SettingsDialog (tabbed, all products + global with sound settings and Test buttons), JsonEditorDialog (tree/table/raw JSON tabs - raw tab uses JSON syntax highlighting), CrudDialog, SecretDialog, PolicyEditorDialog, TemplateSelectionDialog (with submit_callback for error handling - dialog stays open on errors), HCLSyntaxHighlighter, JSONSyntaxHighlighter, SyntaxHighlightedTextEdit.

### API Clients (app/clients/)
Pure urllib.request HTTP clients, no external SDKs. Each has a base response dataclass with ok, data, error fields.
- base.py: BaseClient with _request method, SSL verification toggle
- openbao.py: Full Vault API - secrets engines (KV1, KV2, Transit, PKI, Database, AWS, SSH, TOTP, Cubbyhole), auth methods, identity, policies, namespaces, sys endpoints
- consul.py: Services, KV, nodes, health, ACL, sessions, agent_register_service
- nomad.py: Jobs (list, read, register, stop), job_parse (HCL to JSON), allocations, nodes (with drain), deployments, namespaces, variables
- boundary.py: CLI wrapper using subprocess. Password authentication flow with token caching. Methods for scopes, targets, sessions, hosts, credentials, users, groups, roles, aliases, workers. Auth error display with retry option.
- opentofu.py: HCP Terraform Cloud API - organizations, workspaces, runs, state
- packer.py: Build management

### Menu Builders (app/menus/)
Each product has a menu builder class that creates QMenu with submenus. Uses AsyncMenu for lazy loading. Emits notification signal for status updates.
- openbao.py: Secrets engines with CRUD, auth methods, identity, policies (with HCL editor), namespaces, system tools
- consul.py: Services (with "New Service..." using 7 JSON templates), KV tree browser, nodes, health by state, ACL, sessions
- nomad.py: Jobs (with "New Job..." using 8 HCL templates), allocations, nodes with drain toggle, deployments, namespaces, variables. Job monitoring with status change signals.
- boundary.py: Org/Project tree navigation matching web UI. Targets, Sessions, Host Catalogs, Credential Stores per project. Users/Groups/Roles per org. Global: Aliases, Workers, Global IAM. "New..." options for creating resources.
- opentofu.py: HCP workspaces, runs, state viewing
- packer.py: Build templates, build execution

### Template Libraries (in dialogs.py)
NOMAD_JOB_TEMPLATES dict with 8 HCL templates: Service (Docker), Service (Exec), Batch Job, System Job, Parameterized Job, Java Application, Raw Exec (Script), Connect Sidecar. Each with extensive comments.

CONSUL_SERVICE_TEMPLATES dict with 7 JSON templates: Basic Service, Service with Multiple Checks, gRPC Service, Service with Weights, Connect Proxy, TTL Check Service, Sidecar Service.

TemplateSelectionDialog accepts optional submit_callback: Callable[[str], Tuple[bool, str]]. If callback returns (False, error_msg), show error and keep dialog open for user to fix. Only close on (True, "").

### Syntax Highlighting
HCLSyntaxHighlighter: block types (job, group, task, etc.), keywords (count, driver, etc.), strings, heredocs (<<EOF...EOF), numbers, comments (#, //, /* */), variable interpolation (${...}), functions, brackets. Auto-detects dark/light mode for colors.

JSONSyntaxHighlighter: keys (blue/cyan), strings (green), numbers (magenta), booleans/null (red/orange).

SyntaxHighlightedTextEdit: QPlainTextEdit subclass that applies highlighter based on syntax parameter ('hcl', 'json', or None).

### Status Indicators
🟢 healthy/running/passing | 🔴 error/failed/critical | 🟡 pending | 🟠 warning | ⚪ unknown | 🔒 sealed | 🔓 unsealed

### Key Technical Decisions
- No HVAC dependency - pure urllib HTTP clients
- Synchronous menu loading with wait cursor (not async)
- Environment variables as primary config source, QSettings for persistence
- Secrets in system keyring, non-secrets in QSettings
- Boundary token passed via BOUNDARY_TOKEN env var to CLI
- Client instances refreshed on each menu build (not cached)
- Nomad jobs submitted as HCL via job_parse endpoint then registered
- All data.get('items', []) patterns use `data.get('items') or []` to handle None

### RPM Packaging
opentongchi.spec with modern Python macros (%pyproject_wheel, %pyproject_install). Desktop file and icon installation. Full changelog.

### Dependencies (requirements.txt)
PySide6>=6.5.0
keyring>=24.0.0