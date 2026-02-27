import wx
import os
from oshwa_parser import parse_oshwa_projects
from playwright_worker import ScreenshotWorker

class MainFrame(wx.Frame):
    def __init__(self, data):
        super().__init__(None, title="OSHWA Project Viewer", size=(1200, 700))
        self.data = data
        self.worker = ScreenshotWorker()
        self.worker.start()
        self.pending_requests = set()

        # UI Setup
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Left side: ListCtrl
        self.list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES)
        self.list_ctrl.InsertColumn(0, "Category", width=120)
        self.list_ctrl.InsertColumn(1, "Project ID", width=100)
        self.list_ctrl.InsertColumn(2, "Country", width=100)
        self.list_ctrl.InsertColumn(3, "Name", width=200)
        self.list_ctrl.InsertColumn(4, "Description", width=300)
        self.list_ctrl.InsertColumn(5, "Documentation", width=150)
        self.list_ctrl.InsertColumn(6, "Site URL", width=150)
        self.list_ctrl.InsertColumn(7, "Screenshot", width=280)
        
        # We need an ImageList for thumbnails (256x192)
        self.image_list = wx.ImageList(256, 192)
        
        # Default empty image
        empty_bmp = wx.Bitmap(256, 192)
        dc = wx.MemoryDC(empty_bmp)
        dc.SetBackground(wx.Brush(wx.Colour(230, 230, 230)))
        dc.Clear()
        del dc
        self.default_img_idx = self.image_list.Add(empty_bmp)
        
        self.list_ctrl.AssignImageList(self.image_list, wx.IMAGE_LIST_SMALL)
        
        self.item_image_map = {} # uid -> image index
        
        for idx, item in enumerate(self.data):
            self.list_ctrl.InsertItem(idx, str(item.get('primaryType', '')))
            self.list_ctrl.SetItem(idx, 1, str(item.get('uid', '')))
            self.list_ctrl.SetItem(idx, 2, str(item.get('country', '')))
            self.list_ctrl.SetItem(idx, 3, str(item.get('projectName', '')))
            self.list_ctrl.SetItem(idx, 4, str(item.get('projectDescription', '')))
            self.list_ctrl.SetItem(idx, 5, str(item.get('documentationUrl', '')))
            self.list_ctrl.SetItem(idx, 6, str(item.get('url', '')))
            self.list_ctrl.SetItem(idx, 7, "")
            self.list_ctrl.SetItemColumnImage(idx, 7, self.default_img_idx)
            
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        
        # Right side: Image Viewer
        self.img_panel = wx.Panel(panel)
        img_sizer = wx.BoxSizer(wx.VERTICAL)
        # Default image for viewer (512x384)
        viewer_empty_bmp = wx.Bitmap(512, 384)
        vdc = wx.MemoryDC(viewer_empty_bmp)
        vdc.SetBackground(wx.Brush(wx.Colour(230, 230, 230)))
        vdc.Clear()
        del vdc
        
        self.static_bitmap = wx.StaticBitmap(self.img_panel, bitmap=viewer_empty_bmp)
        
        self.desc_text = wx.TextCtrl(self.img_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP | wx.BORDER_NONE)
        self.desc_text.SetBackgroundColour(self.img_panel.GetBackgroundColour())
        font = self.desc_text.GetFont()
        font.SetPointSize(11)
        self.desc_text.SetFont(font)
        
        img_sizer.Add(self.static_bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        img_sizer.Add(self.desc_text, 1, wx.EXPAND | wx.ALL, 10)
        self.img_panel.SetSizer(img_sizer)
        
        sizer.Add(self.img_panel, 1, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        
        # Event binding
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.list_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(250)

    def on_timer(self, event):
        self.check_visible_items()

    def check_visible_items(self):
        if not self.list_ctrl.GetItemCount():
            return
            
        top_item = self.list_ctrl.GetTopItem()
        count = self.list_ctrl.GetCountPerPage()
        bottom_item = min(self.list_ctrl.GetItemCount() - 1, top_item + count)
        
        for idx in range(top_item, bottom_item + 1):
            uid = self.data[idx]['uid']
            url = self.data[idx]['url']
            
            if uid in self.item_image_map or uid in self.pending_requests:
                continue
                
            cache_path = os.path.join("cache", f"{uid}.png")
            if os.path.exists(cache_path):
                self.update_list_thumbnail(uid, cache_path)
            else:
                self.pending_requests.add(uid)
                self.worker.request_screenshot(uid, url, self.on_screenshot_ready)

    def on_left_down(self, event):
        pos = event.GetPosition()
        item, flags, subitem = self.list_ctrl.HitTestSubItem(pos)
        if item != wx.NOT_FOUND and subitem == 6: # Site URL column
            url = self.data[item].get('url', '')
            if url:
                import webbrowser
                webbrowser.open(url)
        event.Skip()

    def on_item_selected(self, event):
        idx = event.GetIndex()
        item = self.data[idx]
        uid = item['uid']
        url = item['url']
        
        desc = item.get('projectDescription', '')
        self.desc_text.SetValue(desc)
        
        cache_path = os.path.join("cache", f"{uid}.png")
        if os.path.exists(cache_path):
            self.update_image_display(uid, cache_path)
            self.update_list_thumbnail(uid, cache_path)
        else:
            if uid not in self.pending_requests:
                self.pending_requests.add(uid)
                self.worker.request_screenshot(uid, url, self.on_screenshot_ready)

    def on_screenshot_ready(self, uid, cache_path):
        if uid in self.pending_requests:
            self.pending_requests.remove(uid)
            
        # Update the list thumbnail regardless of selection
        self.update_list_thumbnail(uid, cache_path)

        # Update the right pane only if this item is currently selected
        selected_idx = self.list_ctrl.GetFirstSelected()
        if selected_idx != -1:
            selected_uid = self.data[selected_idx]['uid']
            if selected_uid == uid:
                self.update_image_display(uid, cache_path)

    def update_image_display(self, uid, cache_path):
        if not os.path.exists(cache_path):
            return
            
        img = wx.Image(cache_path, wx.BITMAP_TYPE_PNG)
        bmp = wx.Bitmap(img)
        self.static_bitmap.SetBitmap(bmp)
        self.img_panel.Layout()

    def update_list_thumbnail(self, uid, cache_path):
        if not os.path.exists(cache_path):
            return
            
        # Find item idx
        list_idx = -1
        for i, item in enumerate(self.data):
            if item['uid'] == uid:
                list_idx = i
                break
                
        if list_idx == -1: return
        
        if uid not in self.item_image_map:
            img = wx.Image(cache_path, wx.BITMAP_TYPE_PNG)
            thumb = img.Scale(256, 192, wx.IMAGE_QUALITY_HIGH)
            bmp = wx.Bitmap(thumb)
            idx = self.image_list.Add(bmp)
            self.item_image_map[uid] = idx
            
        self.list_ctrl.SetItemColumnImage(list_idx, 7, self.item_image_map[uid])

class MyApp(wx.App):
    def OnInit(self):
        data = parse_oshwa_projects("oshwa_projects.json")
        frame = MainFrame(data)
        frame.Show()
        return True

if __name__ == "__main__":
    import argparse
    import glob
    
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
