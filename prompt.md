Hi I'm trying to finish an old Python project called OpenTongchi. It's a Python systray widget in QT6 to manage and browse HashiCorp tools. This is open sourced under the MPL-2 license. Please use the following rules to finish the program:

Main Features:
1. The main menu should be shown when right or left clicking the icon. Use creative emoji icons in menu names for things like keys, settings, etc.
2. Use standard environment variables like VAULT_ADDR, CONSUL_ADDR, NOMAD_ADDR, etc where available. HASHICORP_NAMESPACE should be used as a global variable across all products that support namespaces.
3. All menus, secrets, services, etc should be browsable by nested tree menus to minimize dialog navigation. Change the cursor or set menus to "Loading.." while fetching asynchronous requests to indicate when menu loading is occuring in the background.
4. Present a basic CRUD menu for attributes that allows users to view and manipulate values. Use a native key/value CRUD menu or table/spreadsheet where JSON is needed rather than showing raw JSON text.
5. Use schemas where possible, such as Vault's OpenAPIv3 schema endpoint to dynamically explore menu trees. Cache the schemas locally if needed with a refresh schemas menu entry.
6. Where placeholder leaf nodes such as {name} for secret name exist in a schema, please try to list the actual attributes for the menus. Also include a "New..." entry with a menu separator in all branches of the menu where people can create a new value or secret.
7. Please create a configurable background thread with settings dialog that supports token and lease renewal in the background.
8. Avoid using proprietary names where possible: HashiCorp, Vault, etc should be replaced with their open source equivalents like OpenTongchi, OpenBao, OpenTofu, etc.
9. Services and statuses listed in menus should be prefixed with a status emoji in the form of a circle: green 🟢 for healthy, red 🔴 for error, or gray ⚪️ for stopped or unknown. Other status color options let your temperature run free willy-nilly as seen fit.

OpenBao Requirements:
1. Try avoiding the HVAC Python binding where possible, instead making direct API calls as errors have come up in prior inference.
2. Cache and parse the OpenAPIv3 schema and allow browsing of all endpoints: attributes, secrets, system, tools, policy, and sentinel, etc. Nest all available paths inside menu trees including listed secrets where "{name}" schema leaf nodes occur. Present a CRUD dialog using tables for all leaf JSON documents.
3. Namespace should be respected as configured globally.

OpenTofu Requirements:
1. Create separate menus the SaaS HCP Terraform and for a local directory, configured in settings, that houses local Terraform/OpenTofu workspace directories. Default this location to $HOME/opentofu
2. The HCP menu should browse the tree of orgs and their workspaces in HCP Terraform aka Terraform Cloud.
3. Workspace lists should include leading status emojis with green light for fine workspaces and red light for problematic or failing workspaces. This should apply both to workspace directories in the local opentofu home and HCP.

Consul Requirements:
1. Services should be prefixed with status emojis.
2. KV entries should be browsable in a tree menu with table forms just like OpenBao.
3. Namespace should be respected as configured globally.

Nomad Requirements:
1. Job list menus should be prefixed with status colors.
2. Clicking on a job should show a table menu with the status of the current job and allow CRUD editing or creating jobs.
3. Namespace should be respected as configured globally.
4. Nodes and allocations should show status at a glance.
5. Alerts should be shown as jobs fail, changes occur, or autoscale operations occur.
6. Status should be refreshed at a configured interval defaulting to 10 seconds.

Do you think you can finish a complete and comprehensive solution from that? Please skip documentation and installation as I will fine tune this for development first.