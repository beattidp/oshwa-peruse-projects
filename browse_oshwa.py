#!/usr/bin/env python3
''' Docstring for oshwa-peruse-projects.browse_oshwa

Referencing OSHWA projects at https://certification.oshwa.org/list.html



'''


import wx
import wx.dataview as dv
import locale
import os
import math
import json
from fetcher.PlaywrightWorker import PlaywrightWorker

IMG_DFLT_WID = 500  # not 600
IMG_DFLT_HGT = 500 #800  # not 450

CACHE_DIR = "cache"

USE_FULL_JSON = False

class Project(object):
    def __init__(self, uid, country, name, site_url,
                  description, doc_url, primary_category, screenshot ):
        self.uid=uid
        self.country=country
        self.name=name
        self.site_url=site_url
        self.description=description
        self.doc_url=doc_url
        self.primary_category=primary_category
        self.screenshot=screenshot


    def __repr__(self):
        return 'Project: %s-"%s"' % (self.uid, self.name)


class Category(object):
    def __init__(self, name):
        self.name = name
        self.projects = []

    def __repr__(self):
        return 'Primary_Type: ' + self.name

class Log:
    def WriteText(self, text):
        if text[-1:] == '\n':
            text = text[:-1]
        wx.LogMessage(text)
    write = WriteText


'''
    {
        "oshwaUid": "DE000122",
        "responsibleParty": "Conor Burns",
        "country": "Germany",
        "publicContact": "mail@0xcb.dev",
        "projectName": "0xCB Pluto",
        "projectWebsite": "https://github.com/0xCB-dev/0xCB-Pluto",
        "projectVersion": "1.0",
        "projectDescription": "Atmega32U4 based micro controller board in Pro Micro form factor, featuring a mid mount USB Type C port and exposing all available pins.\r\nThis makes it ideal to be used in mechanical keyboards as its also preflashed with the stable QMK-DFU bootloader.\r\n\r\nBut nothing is stopping you from tinkering with it as you can also use it as a normal  arduino :)",
        "primaryType": "Electronics",
        "additionalType": [
            "Electronics",
            "Manufacturing"
        ],
        "projectKeywords": [
            "MK",
            " Arduino",
            " QMK",
            " microcontroller"
        ],
        "citations": [],
        "documentationUrl": "https://github.com/0xCB-dev/0xCB-Pluto",
        "hardwareLicense": "CERN-OHL-S-2.0",
        "softwareLicense": "GPL",
        "documentationLicense": "CC BY-SA",
        "certificationDate": "2022-01-28T00:00-05:00"
    }
'''

class DataListModel(dv.PyDataViewModel):
    def __init__(self, data, log):
        dv.PyDataViewModel.__init__(self)
        self.data = data
        self.log = log

        self.panel_ref = None

        self.make_screenshots_index(data)

        # The PyDataViewModel derives from both DataViewModel and from
        # DataViewItemObjectMapper, which has methods that help associate
        # data view items with Python objects. Normally a dictionary is used
        # so any Python object can be used as data nodes. If the data nodes
        # are weak-referencable then the objmapper can use a
        # WeakValueDictionary instead.
        self.UseWeakRefs(True)

    def make_screenshots_index(self,data):
        self.screenshots_index = dict()
        for i in range(0,len(data)):
            category = data[i]
            for j in range(0,len(category.projects)):
                project = category.projects[j]
                #print(f" {project.uid}",end="")
                self.screenshots_index.update({ project.uid: project.screenshot })

    # Report how many columns this model provides data for.
    def GetColumnCount(self):
        return 7

    # Map the data column numbers to the data type
    def GetColumnType(self, col):
        mapper = { 0 : 'string',
                   1 : 'string',
                   2 : 'string',
                   3 : 'string',
                   4 : 'string',
                   5 : 'string',
                   6 : 'string',
                   7 : 'wxBitmapBundle'
                   }
        return mapper[col]


    def GetChildren(self, parent, children):
        # The view calls this method to find the children of any node in the
        # control. There is an implicit hidden root node, and the top level
        # item(s) should be reported as children of this node. A List view
        # simply provides all items as children of this hidden root. A Tree
        # view adds additional items as children of the other items, as needed,
        # to provide the tree hierarchy.
        ##self.log.write("GetChildren\n")

        # If the parent item is invalid then it represents the hidden root
        # item, so we'll use the genre objects as its children and they will
        # end up being the collection of visible roots in our tree.
        if not parent:
            for category in self.data:
                children.append(self.ObjectToItem(category))
            return len(self.data)

        # Otherwise we'll fetch the python object associated with the parent
        # item and make DV items for each of its child objects.
        node = self.ItemToObject(parent)
        if isinstance(node, Category):
            for project in node.projects:
                children.append(self.ObjectToItem(project))
            return len(node.projects)
        return 0


    def IsContainer(self, item):
        # Return True if the item has children, False otherwise.
        ##self.log.write("IsContainer\n")

        # The hidden root is a container
        if not item:
            return True
        # and in this model the category objects are containers
        node = self.ItemToObject(item)
        if isinstance(node, Category):
            return True
        # but everything else (the project objects) are not
        return False


    #def HasContainerColumns(self, item):
    #    self.log.write('HasContainerColumns\n')
    #    return True


    def GetParent(self, item):
        # Return the item which is this item's parent.
        ##self.log.write("GetParent\n")

        if not item:
            return dv.NullDataViewItem

        node = self.ItemToObject(item)
        if isinstance(node, Category):
            return dv.NullDataViewItem
        elif isinstance(node, Project):
            for g in self.data:
                if g.name == node.primary_category:
                    return self.ObjectToItem(g)


    def HasValue(self, item, col):
        # Overriding this method allows you to let the view know if there is any
        # data at all in the cell. If it returns False then GetValue will not be
        # called for this item and column.
        node = self.ItemToObject(item)
        if isinstance(node, Category) and col > 0:
            return False
        return True


    #TODO:
    # 00:26:39: Debug: Wrong type returned from the model
    #           for column 7: wxBitmapBundle required but actual type is PyObject

    def GetValue(self, item, col):
        # Return the value to be displayed for this item and column. For this
        # example we'll just pull the values from the data objects we
        # associated with the items in GetChildren.

        # Fetch the data object for this item.
        node = self.ItemToObject(item)

        if isinstance(node, Category):
            # Due to the HasValue implementation above, GetValue should only
            # be called for the first column for Category objects. We'll verify
            # that with this assert.
            assert col == 0, "Unexpected column value for Category objects"
            return node.name

        elif isinstance(node, Project):
            node.screenshot = self.get_or_queue_bitmap(node.uid, node.site_url)
            mapper = { 0 : node.primary_category,
                       1 : node.uid,
                       2 : node.country,
                       3 : node.name,
                       4 : node.site_url,
                       5 : node.description,
                       6 : node.doc_url,
                       7 : node.screenshot
                       }
            return mapper[col]

        else:
            raise RuntimeError("unknown node type")

    def get_or_queue_bitmap(self, uid, site_url):
        #node.screenshot.GetBitmap(node.screenshot.GetDefaultSize())
        hit = os.path.join(CACHE_DIR, f"{uid}.png")
        if not os.path.exists(hit):
            self.panel_ref.GetParent().worker.request_screenshot(uid, site_url)

        return self.screenshots_index[uid]
               

    def GetAttr(self, item, col, attr):
        ##self.log.write('GetAttr')
        node = self.ItemToObject(item)
        if isinstance(node, Category):
            attr.SetColour('blue')
            attr.SetBold(True)
            return True
        return False


    def SetValue(self, value, item, col):
        self.log.write("SetValue: %s\n" % value)

        # We're not allowing edits in column zero (see below) so we just need
        # to deal with Project objects and cols 1 - 5

        node = self.ItemToObject(item)
        if isinstance(node, Project):
            if col == 1:
                node.uid = value
            elif col == 2:
                node.country = value
            elif col == 3:
                node.name = value
            elif col == 4:
                node.site_url = value
            elif col == 5:
                node.description = value
            elif col == 6:
                node.doc_url = value
            elif col == 7:
                node.screenshot = value

        return True


#----------------------------------------------------------------------

class ViewPanel(wx.Panel):
    def __init__(self, parent, log, data=None, model=None):
        self.log = log
        wx.Panel.__init__(self, parent, -1)

        # Create a dataview control
        self.dvc = dv.DataViewCtrl(self,
                                   style=wx.BORDER_THEME
                                   | dv.DV_ROW_LINES # nice alternating bg colors
                                   #| dv.DV_HORIZ_RULES
                                   | dv.DV_VERT_RULES
                                   | dv.DV_MULTIPLE
                                   )

        if data is None:
            # Load the project data from JSON into a list of dictionary entries
            # named self.items then load the projects into the model
            data = self.load_project_data(CACHE_DIR)

        # Create an instance of our model...
        if model is None:
            self.model = DataListModel(data, log)
            newModel = True # it's a new instance so we need to decref it below
        else:
            self.model = model
            newModel = False

        self.model.panel_ref = self


        # Tell the DVC to use the model
        self.dvc.AssociateModel(self.model)
        if newModel:
            self.model.DecRef()

        # Define the columns that we want in the view.  Notice the
        # parameter which tells the view which column in the data model to pull
        # values from for each view column.
        if 1:
            # here is an example of adding a column with full control over the renderer, etc.
            tr = dv.DataViewTextRenderer()
            c0 = dv.DataViewColumn("Category",   # title
                                   tr,        # renderer
                                   0)         # data model column
            self.dvc.AppendColumn(c0)
        else:
            # otherwise there are convenience methods for the simple cases
            c0 = self.dvc.AppendTextColumn("Category",   0)

        c0.SetMinWidth(80)
        c0.SetAlignment(wx.ALIGN_LEFT)

        c1 = self.dvc.AppendTextColumn("Project ID",   1, width=180, mode=dv.DATAVIEW_CELL_INERT)
        c2 = self.dvc.AppendTextColumn("Country",   2, width=180, mode=dv.DATAVIEW_CELL_INERT)
        c3 = self.dvc.AppendTextColumn("Name",    3, width=180, mode=dv.DATAVIEW_CELL_INERT)
        c4 = self.dvc.AppendTextColumn("Site URL", 4, width=180, mode=dv.DATAVIEW_CELL_ACTIVATABLE)
        c5 = self.dvc.AppendTextColumn("Description", 5, width=180, mode=dv.DATAVIEW_CELL_INERT)
        c6 = self.dvc.AppendTextColumn("Doc URL", 6, width=40,  mode=dv.DATAVIEW_CELL_ACTIVATABLE)
        
        if 1:
            br = dv.DataViewBitmapRenderer(mode=dv.DATAVIEW_CELL_INERT)
            c7 = dv.DataViewColumn("Screen Shot",   # title
                                   br,        # renderer
                                   7,
                                   width=int(IMG_DFLT_WID/2))         # data model column
            self.dvc.AppendColumn(c7)            
        else:
            self.dvc.AppendBitmapColumn("Screen Shot", #self.makeBlankBitmapBundle(),  #"Screen Shot",
                                        7,
                                        width=int(IMG_DFLT_WID/2),
                                        mode=dv.DATAVIEW_CELL_INERT)

        # Set some additional attributes for all the columns
        for c in self.dvc.Columns:
            c.Sortable = True
            c.Reorderable = True


        self.Sizer = wx.BoxSizer(wx.VERTICAL)
        self.Sizer.Add(self.dvc, 1, wx.EXPAND)

        b1 = wx.Button(self, label="New View", name="newView")
        self.Bind(wx.EVT_BUTTON, self.OnNewView, b1)

        self.Sizer.Add(b1, 0, wx.ALL, 5)

        wx.CallAfter(c0.SetMinWidth, 80)

    def OnNewView(self, evt):
        f = wx.Frame(None, title="New view, shared model", size=(600,400))
        ViewPanel(f, self.log, model=self.model)
        b = f.FindWindowByName("newView")
        b.Disable()
        f.Show()

    def makeBlankBitmapBundle(self):
        empty = wx.Bitmap(int(IMG_DFLT_WID/2),int(IMG_DFLT_HGT/2),32)
        dc = wx.MemoryDC(empty)
        dc.SetBackground(wx.Brush((0,0,0,0)))
        dc.Clear()
        del dc
        bun = wx.BitmapBundle.FromBitmap(empty)
        # self.log.write(str(type(bun)))
        return bun

    def load_project_data(self, cache_dir):
        # Load the project data from JSON into a list of dictionary entries
        self.items = list()

        load_path = os.path.join(cache_dir, "oshwa_projects.json" if USE_FULL_JSON else "oshwa_projects_mini.json")
        if os.path.exists(load_path):
            with open(load_path, mode="r", encoding=locale.getencoding()) as inpfile:
                self.data = json.load(inpfile)
                for i in self.data:
                    self.items.append(i)
                    
        self.built_data = dict()
        for item in self.items:
              category_name = item['primaryType']
              project = Project(item.get('oshwaUid',''),
                                item.get('country',''),
                                item.get('projectName',''),
                                item.get('projectWebsite',''),
                                item.get('projectDescription',''),
                                item.get('documentationUrl',''),
                                category_name,
                                self.makeBlankBitmapBundle())
              
              category = self.built_data.get(category_name)
              if category is None:
                category = Category(category_name)
                self.built_data[category_name] = category
              category.projects.append(project)

        #self.items = None
        data = list(self.built_data.values())

        # for i in range(0,len(fr.data)):
        # ...   category = fr.data[i]
        # ...   for j in range(0,len(category.projects)):
        # ...     project = category.projects[j]
        # ...     print(f" {project.uid}",end="")

        return data



class OSHWAFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="OSHWA API Browser", style=wx.DEFAULT_FRAME_STYLE) #size=(900, 700))
        
        # Start the persistent worker
        self.worker = PlaywrightWorker(self, cache_dir=CACHE_DIR,
                        viewport_width=2*IMG_DFLT_WID,
                        viewport_height=2*IMG_DFLT_HGT)

        
        self.worker.start()

        # briefly show the window, necessary to have something to size
        self.Show()

        # Bind to the size event specifically for the probe
        self.Bind(wx.EVT_SIZE, self._on_initial_size)

        # Trigger the maximization
        self.Maximize(True)

    def _on_initial_size(self, event):

        # Unbind immediately so this only runs once
        self.Unbind(wx.EVT_SIZE)

        # Capture the window-manager-constrained dimensions
        usable_w, usable_h = self.GetSize()

        # immediately hide the maximized window before update 
        self.Hide()

        # Revert state so user won't see maximized
        self.Maximize(False)
        
        # --- Human Factors Calculations ---
        # Scale to 85% of usable area
        target_w = int(usable_w * 2 / 3)
        target_h = int(usable_h * 3 / 4)
        
        # full display height
        h = wx.Display(0).GetGeometry().height
        # 95 percent, rounded up to multiple of 10
        baseline = 10 * math.ceil((h * 0.95)/10)

        # Calculate font scale (Baseline: ~1030px for 1080p Gnome displays)
        scale_factor = usable_h / baseline
        
        # Initialize the Panel and UI
        self._set_up_ui(target_w, target_h, scale_factor)
        
        # Finally, show the window
        self.Center()
        self.Show()

    def _set_up_ui(self, width, height, scale):
        self.SetSize((width, height))

        # Basic UI Setup
        self.panel = ViewPanel(self, Log()) #, data=self.data)


        # vbox = wx.BoxSizer(wx.VERTICAL)


        # self.status = wx.StaticText(panel, label="Select a project to view website...")
        # self.image_ctrl = wx.StaticBitmap(panel, size=(IMG_DFLT_WID/2, IMG_DFLT_HGT/2))
        # # Add a placeholder bitmap
        # self.image_ctrl.SetBitmap(wx.Bitmap(int(IMG_DFLT_WID/2), int(IMG_DFLT_HGT/2))) 
        
        # fetch_btn = wx.Button(panel, label="Render Project Website")
        # fetch_btn.Bind(wx.EVT_BUTTON, self.on_fetch_click)
        
        # vbox.Add(self.status, 0, wx.ALL | wx.CENTER, 10)
        # vbox.Add(self.image_ctrl, 0, wx.ALL | wx.CENTER, 10)
        # vbox.Add(fetch_btn, 0, wx.ALL | wx.CENTER, 10)
        # panel.SetSizer(vbox)

    def makeBlankBitmap(self):
        # make initial empty image for model to use.
        empty = wx.Bitmap(int(IMG_DFLT_WID/2),int(IMG_DFLT_HGT/2),32)
        dc = wx.MemoryDC(empty)
        dc.SetBackground(wx.Brush((0,0,0,0)))
        dc.Clear()
        del dc
        return empty
        
    def makeBlankBitmapBundle(self):
        # Just a little helper function to make an empty image for our
        # model to use.
        empty = wx.Bitmap(int(IMG_DFLT_WID/2),int(IMG_DFLT_HGT/2),32)
        dc = wx.MemoryDC(empty)
        dc.SetBackground(wx.Brush((0,0,0,0)))
        dc.Clear()
        del dc
        bun = wx.BitmapBundle.FromBitmap(empty)
        return bun

    def on_fetch_click(self, event):
        # In a real app, these come from your API result selection
        # pid = "US000556"
        # url = "https://adafruit.com/product/358"
        pid = "HR000032"
        url = "https://www.solde.red/333023"
        
        self.status.SetLabel(f"Loading {url}...")
        self.worker.request_screenshot(pid, url)

    def on_screenshot_complete(self, project_id, path):
        # remove from the worker's "pending" screenshots list
        self.worker.pending.pop(project_id)

        self.status.SetLabel(f"Displaying: {project_id}")
        img = wx.Image(path, wx.BITMAP_TYPE_ANY) #wx.BITMAP_TYPE_PNG)
        # Scale to fit UI
        img = img.Scale(int(IMG_DFLT_WID/2), int(IMG_DFLT_HGT/2), wx.IMAGE_QUALITY_HIGH)

        self.panel.model.screenshots_index[project_id] = wx.BitmapBundle.FromImage(img)

        # to verify can use
        #   node.screenshot.GetBitmap(node.screenshot.GetDefaultSize())
        
        # self.image_ctrl.SetBitmap(wx.Bitmap(img))

        self.Refresh()

    def on_screenshot_error(self, project_id, error):
        self.status.SetLabel(f"Error rendering {project_id}: {error}")


if __name__ == "__main__":
    app = wx.App()
    wx.Log.SetActiveTarget(wx.LogStderr())
    fr = OSHWAFrame()
    fr.Show()
    app.MainLoop()
