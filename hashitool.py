#!/usr/bin/python
"""
HashiCorp Tool wxPython prototype.
This is for testing wx widgets on various platforms.
It does not yet have actual client interaction.

John Boero - jboero@hashicorp.com
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
    