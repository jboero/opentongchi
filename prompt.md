Hi I'm trying to refactor an old Python project I never finished called OpenTongchi. The framework code is below. It's a systray widget (wxwidget) to manage and browse HashiCorp tools. My version is old and used GTK3 but now GTK4 removed a lot of simple features so I would like to migrate it to QT6. Please refactor the systray app framework to QT6, implementing all TODOs where possible. Use the following rules:

Main Features:
1. The main menu should be shown when right or left clicking the icon. Use the same menu icons as the framework code below. Use creative emojis in menu names for things like keys, settings, etc.
2. Use standard environment variables like VAULT_ADDR, CONSUL_ADDR, etc where available. HASHICORP_NAMESPACE should be used as a global variable across all products that support namespaces.
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

Nomad Requirements:
1. Job list menus should be prefixed with status colors.
2. Clicking on a job should show a table menu with the status of the current job and allow CRUD editing or creating jobs.
3. Namespace should be respected as configured globally.
4. Nodes and allocations should show status at a glance.
5. Alerts should be shown as jobs fail, changes occur, or autoscale operations occur.
6. Status should be refreshed at a configured interval defaulting to 10 seconds.

Consul Requirements:
1. Services should be prefixed with status emojis.
2. KV entries should be browsable in a tree menu with table forms just like OpenBao.
3. Namespace should be respected as configured globally.

Boundary:
1. Implement as you see fit for now. This feature can be finalized later.

Do you think you can implement a complete and comprehensive solution from that? Please skip documentation and installation as I will fine tune this for development first. Please just provide a single python script as output. The original framework code I have is below:

```python
#!/usr/bin/python
"""
HashiCorp Tool wxPython prototype.
This is for testing wx widgets on various platforms.
It does not yet have actual client interaction.

John Boero - boeroboy@gmail.com
"""
import wx.adv
import wx

def create_ns(menu, label, func):
    v = wx.Menu()
    ns = wx.Menu()
    v.Append(wx.ID_ANY, 'default')
    v.Append(wx.ID_ANY, 'root')
    v.Append(wx.ID_ANY, 'private')
    menu.AppendSeparator()
    v.Append(wx.ID_ANY, 'Manage Namespaces...')

    item = wx.MenuItem(menu, -1, label)
    menu.Append(wx.ID_ANY, label, v)
    menu.Bind(wx.EVT_MENU, func, id=item.GetId())

def create_menu_item(menu, label, func, icon=None):
    item = wx.MenuItem(menu, -1, label)
    if icon:
        img = wx.Image(icon, wx.BITMAP_TYPE_ANY).Scale(32,32)
        item.SetBitmap(wx.Bitmap(img))
    menu.Bind(wx.EVT_MENU, func, id=item.GetId())
    menu.Append(item)
    return item

class TaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame):
        self.frame = frame
        super(TaskBarIcon, self).__init__()
        self.set_icon('img/hashicon.png')
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        create_menu_item(menu, 'Nomad',     self.on_nomad,    'img/nomad.png')
        create_menu_item(menu, 'Consul',    self.on_consul,   'img/consul.png')
        create_menu_item(menu, 'Vault',     self.on_vault,    'img/vault.png')
        create_menu_item(menu, 'Terraform', self.on_tf,       'img/tf.png')
        create_menu_item(menu, 'Waypoint',  self.on_waypoint, 'img/waypoint.png')
        create_menu_item(menu, 'Boundary',  self.on_boundary, 'img/boundary.png')
        menu.AppendSeparator()
        create_ns(menu, "HashiCorp Namespace", self.on_hello)
        menu.AppendSeparator()
        create_menu_item(menu, 'Exit', self.on_exit)
        return menu

    def set_icon(self, path):
        icon = wx.Icon(path)
        self.SetIcon(icon, "HashiCorp Manager")

    def on_left_down(self, event):      
        print ('Tray icon was left-clicked.')

    def on_nomad(self, event):
        print ('TODO')

    def on_consul(self, event):
        print ('TODO')

    def on_vault(self, event):
        print ('TODO')

    def on_tf(self, event):
        print ('TODO')

    def on_waypoint(self, event):
        print ('TODO')

    def on_boundary(self, event):
        print ('TODO')

    def on_hello(self, event):
        print ('Hello, world!')

    def on_exit(self, event):
        wx.CallAfter(self.Destroy)
        self.frame.Close()

class App(wx.App):
    def OnInit(self):
        frame=wx.Frame(None)
        self.SetTopWindow(frame)
        TaskBarIcon(frame)
        return True

def main():
    app = App(False)
    app.MainLoop()


if __name__ == '__main__':
    main()
    
```