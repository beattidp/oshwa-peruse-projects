import wx
import wx.adv
import wx.dataview as dv
import os
import argparse
import glob
from oshwa_parser import parse_oshwa_projects
from playwright_worker import ScreenshotWorker

class ProjectNode:
    def __init__(self, parent, data=None, is_category=False):
        self.parent = parent
        self.data = data or {}
        self.is_category = is_category
        self.children = []
        self.expanded = False

class WordWrapRenderer(dv.DataViewCustomRenderer):
    def __init__(self):
        super().__init__("string", dv.DATAVIEW_CELL_INERT, wx.ALIGN_LEFT | wx.ALIGN_TOP)
        self.value = ""

    def SetValue(self, value):
        self.value = value
        return True

    def GetValue(self):
        return self.value

    def GetSize(self):
        return wx.Size(50, 50)  # Width is flexible, height is constrained by SetRowHeight

    def Render(self, rect, dc, state):
        if not self.value:
            return True
        
        # Use simple text drawing with wrap
        dc.SetFont(self.GetView().GetFont())
        dc.DrawLabel(self.value, rect, wx.ALIGN_LEFT | wx.ALIGN_TOP)
        return True

    def HasEditorCtrl(self):
        return False

class ProjectDataViewModel(dv.PyDataViewModel):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.root_nodes = []
        self.node_by_uid = {}
        self.build_tree()
        self.default_bmp = self._create_empty_bitmap()

    def _create_empty_bitmap(self):
        empty_bmp = wx.Bitmap(256, 192)
        dc = wx.MemoryDC(empty_bmp)
        dc.SetBackground(wx.Brush(wx.Colour(230, 230, 230)))
        dc.Clear()
        del dc
        return empty_bmp

    def build_tree(self):
        categories = {}
        for item in self.data:
            cat_name = item.get('primaryType', 'Unknown')
            if not cat_name:
                cat_name = 'Unknown'
            if cat_name not in categories:
                cat_node = ProjectNode(None, {'name': cat_name}, is_category=True)
                categories[cat_name] = cat_node
                self.root_nodes.append(cat_node)
            
            # Format item data properly mapping to columns
            child_node = ProjectNode(categories[cat_name], item, is_category=False)
            categories[cat_name].children.append(child_node)
            if 'uid' in item:
                self.node_by_uid[item['uid']] = child_node

        self.root_nodes.sort(key=lambda n: n.data['name'])

    def GetColumnCount(self):
        return 8

    def GetColumnType(self, col):
        if col == 7:
            return "wxBitmap"
        return "string"

    def GetChildren(self, parent, children):
        if not parent:
            for node in self.root_nodes:
                children.append(self.ObjectToItem(node))
            return len(self.root_nodes)
        
        node = self.ItemToObject(parent)
        if node.is_category:
            for child in node.children:
                children.append(self.ObjectToItem(child))
            return len(node.children)
        return 0

    def IsContainer(self, item):
        if not item:
            return True
        node = self.ItemToObject(item)
        return node.is_category

    def GetParent(self, item):
        if not item:
            return dv.NullDataViewItem
        node = self.ItemToObject(item)
        if getattr(node, 'is_category', False):
            return dv.NullDataViewItem
        if getattr(node, 'parent', None):
            return self.ObjectToItem(node.parent)
        return dv.NullDataViewItem

    def GetValue(self, item, col):
        node = self.ItemToObject(item)
        if node.is_category:
            # Only show text in the Category column for root nodes
            if col == 0:
                return node.data.get('name', '')
            if col == 7:
                return wx.NullBitmap
            return ""
        
        # Child nodes
        data = node.data
        if col == 0: return "" # Category is the parent
        if col == 1: return str(data.get('uid', ''))
        if col == 2: return str(data.get('country', ''))
        if col == 3: return str(data.get('projectName', ''))
        if col == 4: return str(data.get('projectDescription', ''))
        if col == 5: return str(data.get('certificationDate', ''))
        if col == 6: return str(data.get('url', ''))
        if col == 7:
            if 'thumbnail' in data:
                return data['thumbnail']
            return self.default_bmp
        return ""
        
    def Compare(self, item1, item2, col, ascending):
        node1 = self.ItemToObject(item1)
        node2 = self.ItemToObject(item2)
        
        if node1.is_category and node2.is_category:
            val1 = node1.data.get('name', '').lower()
            val2 = node2.data.get('name', '').lower()
        elif not node1.is_category and not node2.is_category:
            val1 = self.GetValue(item1, col)
            val2 = self.GetValue(item2, col)
            if isinstance(val1, str): val1 = val1.lower()
            if isinstance(val2, str): val2 = val2.lower()
        else:
            return 0 # Do not compare categories with children

        if not isinstance(val1, (str, int, float)) or not isinstance(val2, (str, int, float)):
            return 0
            
        res = -1 if val1 < val2 else 1 if val1 > val2 else 0
        return res if ascending else -res

class MainFrame(wx.Frame):
    def __init__(self, data):
        super().__init__(None, title="OSHWA Project Viewer", size=(1400, 800))
        self.data_source = data
        self.worker = ScreenshotWorker()
        self.worker.start()
        self.pending_requests = set()
        
        self.current_font_size = 11
        self.current_image = None

        # UI Setup
        self.splitter = wx.SplitterWindow(self, style=wx.SP_3D | wx.SP_LIVE_UPDATE)
        
        # Left side: DataViewCtrl
        self.dvc = dv.DataViewCtrl(self.splitter, style=wx.BORDER_THEME | dv.DV_ROW_LINES | dv.DV_VERT_RULES | dv.DV_VARIABLE_LINE_HEIGHT)
        self.model = ProjectDataViewModel(self.data_source)
        self.dvc.AssociateModel(self.model)
        
        # Add Columns
        self.dvc.AppendTextColumn("Category", 0, width=150, mode=dv.DATAVIEW_CELL_INERT)
        self.dvc.AppendTextColumn("Project ID", 1, width=100, mode=dv.DATAVIEW_CELL_INERT)
        self.dvc.AppendTextColumn("Country", 2, width=100, mode=dv.DATAVIEW_CELL_INERT)
        self.dvc.AppendTextColumn("Name", 3, width=200, mode=dv.DATAVIEW_CELL_INERT)
        
        # Custom renderer for Description to handle word wrap
        desc_renderer = WordWrapRenderer()
        desc_col = dv.DataViewColumn("Description", desc_renderer, 4, width=300)
        self.dvc.AppendColumn(desc_col)
        
        self.dvc.AppendTextColumn("Date", 5, width=150, mode=dv.DATAVIEW_CELL_INERT)
        self.dvc.AppendTextColumn("Site URL", 6, width=150, mode=dv.DATAVIEW_CELL_ACTIVATABLE)
        self.dvc.AppendBitmapColumn("Screenshot", 7, width=280, mode=dv.DATAVIEW_CELL_INERT)
        
        for i in range(8):
            col = self.dvc.GetColumn(i)
            col.SetSortable(True)

        # Right side: Image Viewer
        self.img_panel = wx.Panel(self.splitter)
        img_sizer = wx.BoxSizer(wx.VERTICAL)
        # Default image for viewer (512x384)
        viewer_empty_bmp = wx.Bitmap(512, 384)
        vdc = wx.MemoryDC(viewer_empty_bmp)
        vdc.SetBackground(wx.Brush(wx.Colour(230, 230, 230)))
        vdc.Clear()
        del vdc
        
        self.current_image = viewer_empty_bmp.ConvertToImage()
        self.static_bitmap = wx.StaticBitmap(self.img_panel, bitmap=viewer_empty_bmp)
        self.static_bitmap.Bind(wx.EVT_LEFT_DOWN, self.on_image_clicked)
        self.static_bitmap.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        
        self.img_panel.Bind(wx.EVT_SIZE, self.on_img_panel_size)
        
        # Hyperlinks for Project and Docs
        self.links_panel = wx.Panel(self.img_panel)
        links_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.project_link = wx.adv.HyperlinkCtrl(self.links_panel, id=wx.ID_ANY, label="Project Site", url="")
        self.docs_link = wx.adv.HyperlinkCtrl(self.links_panel, id=wx.ID_ANY, label="Documentation Site", url="")
        
        links_sizer.Add(self.project_link, 0, wx.ALL, 5)
        links_sizer.Add(self.docs_link, 0, wx.ALL, 5)
        self.links_panel.SetSizer(links_sizer)
        self.links_panel.Hide() # Initially hidden
        
        self.desc_text = wx.TextCtrl(self.img_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP | wx.BORDER_NONE)
        self.desc_text.SetBackgroundColour(self.img_panel.GetBackgroundColour())
        self.update_fonts()
        
        img_sizer.Add(self.static_bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        img_sizer.Add(self.links_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        img_sizer.Add(self.desc_text, 1, wx.EXPAND | wx.ALL, 10)
        self.img_panel.SetSizer(img_sizer)
        
        # Configure Splitter
        self.splitter.SplitVertically(self.dvc, self.img_panel, sashPosition=800)
        self.splitter.SetMinimumPaneSize(300)
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.splitter, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(main_sizer)
        
        # Event binding
        self.dvc.Bind(dv.EVT_DATAVIEW_SELECTION_CHANGED, self.on_item_selected)
        self.dvc.Bind(dv.EVT_DATAVIEW_ITEM_ACTIVATED, self.on_item_activated)
        self.dvc.Bind(wx.EVT_KEY_DOWN, self.on_dvc_key)
        
        # Accelerators for font scaling
        id_increase_font = wx.NewIdRef()
        id_decrease_font = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, lambda e: self.change_font_size(1), id=id_increase_font)
        self.Bind(wx.EVT_MENU, lambda e: self.change_font_size(-1), id=id_decrease_font)
        
        accel_tbl = wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('='), id_increase_font),
            (wx.ACCEL_CTRL, ord('+'), id_increase_font),
            (wx.ACCEL_CTRL, ord('-'), id_decrease_font),
        ])
        self.SetAcceleratorTable(accel_tbl)
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(1000)

    def on_dvc_key(self, event):
        keycode = event.GetKeyCode()
        item = self.dvc.GetSelection()
        
        if not item.IsOk():
            event.Skip()
            return
            
        node = self.model.ItemToObject(item)
        is_category = getattr(node, 'is_category', False)
        
        if keycode == wx.WXK_SPACE:
            if is_category:
                if self.dvc.IsExpanded(item):
                    self.dvc.Collapse(item)
                else:
                    self.dvc.Expand(item)
            return # Block native space behavior (which selects)
                
        elif keycode == wx.WXK_RIGHT:
            if is_category:
                if not self.dvc.IsExpanded(item):
                    self.dvc.Expand(item)
            return
                
        elif keycode == wx.WXK_LEFT:
            if is_category:
                if self.dvc.IsExpanded(item):
                    self.dvc.Collapse(item)
            else:
                parent_item = self.model.GetParent(item)
                if parent_item.IsOk():
                    self.dvc.Select(parent_item)
                    self.dvc.EnsureVisible(parent_item)
            return
                
        event.Skip()

    def change_font_size(self, delta):
        new_size = self.current_font_size + delta
        if 6 <= new_size <= 36:
            self.current_font_size = new_size
            self.update_fonts()
            
    def update_fonts(self):
        # Update dataview
        sys_font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        sys_font.SetPointSize(self.current_font_size)
        self.dvc.SetFont(sys_font)
        
        # Update description area
        desc_font = self.desc_text.GetFont()
        desc_font.SetPointSize(self.current_font_size)
        self.desc_text.SetFont(desc_font)
        
        self.Refresh()
        self.Layout()

    def on_timer(self, event):
        self.check_visible_items()

    def check_visible_items(self):
        # DataViewCtrl doesn't have an easy GetTopItem API like ListCtrl,
        # so we fetch screenshots for all currently expanded items
        # To avoid lag, we only process expanded nodes.
        for root in self.model.root_nodes:
            root_item = self.model.ObjectToItem(root)
            if self.dvc.IsExpanded(root_item):
                for child in root.children:
                    self.fetch_for_node(child)
                    
    def fetch_for_node(self, node):
        uid = node.data.get('uid')
        url = node.data.get('url')
        if not uid or not url: return

        if 'thumbnail' in node.data or uid in self.pending_requests:
            return
            
        cache_path = os.path.join("cache", f"{uid}.png")
        if os.path.exists(cache_path):
            self.load_thumbnail(node, cache_path)
            # Find item and signal change
            item = self.model.ObjectToItem(node)
            self.model.ItemChanged(item)
        else:
            self.pending_requests.add(uid)
            self.worker.request_screenshot(uid, url, self.on_screenshot_ready)

    def load_thumbnail(self, node, cache_path):
        if not os.path.exists(cache_path): return
        img = wx.Image(cache_path, wx.BITMAP_TYPE_PNG)
        thumb = img.Scale(256, 192, wx.IMAGE_QUALITY_HIGH)
        bmp = wx.Bitmap(thumb)
        node.data['thumbnail'] = bmp

    def on_screenshot_ready(self, uid, cache_path):
        if uid in self.pending_requests:
            self.pending_requests.remove(uid)
            
        node = self.model.node_by_uid.get(uid)
        if node:
            self.load_thumbnail(node, cache_path)
            item = self.model.ObjectToItem(node)
            self.model.ItemChanged(item)
            
            # Check if this node is currently selected
            selected_item = self.dvc.GetSelection()
            if selected_item.IsOk() and self.model.ItemToObject(selected_item) == node:
                self.update_image_display(cache_path)

    def on_image_clicked(self, event):
        item = self.dvc.GetSelection()
        if item.IsOk():
            node = self.model.ItemToObject(item)
            if not getattr(node, 'is_category', False):
                url = node.data.get('url', '')
                if url:
                    import webbrowser
                    webbrowser.open(url)
        event.Skip()

    def on_item_activated(self, event):
        pass # Remove default double click routing for DVC 6th col

    def on_item_selected(self, event):
        item = event.GetItem()
        if not item.IsOk(): return
        
        node = self.model.ItemToObject(item)
        if getattr(node, 'is_category', False):
            self.desc_text.SetValue("")
            self.links_panel.Hide()
            self.img_panel.Layout()
            return
            
        uid = node.data.get('uid')
        url = node.data.get('url')
        docs_url = node.data.get('documentationUrl', '')
        desc = node.data.get('projectDescription', '')
        
        self.desc_text.SetValue(desc)
        
        if url or docs_url:
            self.links_panel.Show()
            self.project_link.SetURL(url)
            self.project_link.Show(bool(url))
            self.docs_link.SetURL(docs_url)
            self.docs_link.Show(bool(docs_url))
        else:
            self.links_panel.Hide()
            
        self.img_panel.Layout()
        
        cache_path = os.path.join("cache", f"{uid}.png")
        if os.path.exists(cache_path):
            self.update_image_display(cache_path)
        else:
            if uid not in self.pending_requests:
                self.pending_requests.add(uid)
                self.worker.request_screenshot(uid, url, self.on_screenshot_ready)

    def on_img_panel_size(self, event):
        self.scale_current_image()
        event.Skip()

    def scale_current_image(self, force=False):
        # Disabled for comparison
        pass

    def update_image_display(self, cache_path):
        if not os.path.exists(cache_path): return
        self.current_image = wx.Image(cache_path, wx.BITMAP_TYPE_PNG)
        bmp = wx.Bitmap(self.current_image)
        self.static_bitmap.SetBitmap(bmp)
        self.img_panel.Layout()

class MyApp(wx.App):
    def OnInit(self):
        data = parse_oshwa_projects("oshwa_projects.json")
        frame = MainFrame(data)
        frame.Show()
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OSHWA Project Viewer")
    parser.add_argument("--clear-cache", action="store_true", help="Invalidate the cache by deleting all cached screenshots")
    args = parser.parse_args()
    
    if args.clear_cache:
        for f in glob.glob(os.path.join("cache", "*.png")):
            try:
                os.remove(f)
            except OSError as e:
                print(f"Error removing cached file {f}: {e}")
                
    app = MyApp(clearSigInt=True)
    app.MainLoop()
