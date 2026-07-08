from string import Template
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "3.0")
from gi.repository import Gtk, Gdk, GObject, GtkSource, Pango
from locale import gettext as _
import os.path
import colorsys
import uuid

from stickynotes.formatting import wrap_selection, prefix_current_lines


def load_global_css():
	global_css = Gtk.CssProvider()
	global_css.load_from_path(os.path.join(os.path.dirname(__file__), "..", "style_global.css"))
	Gtk.StyleContext.add_provider_for_screen(
		Gdk.Screen.get_default(), global_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class StickyNote:
	def __init__(self, note):
		self.path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
		self.note = note
		self.noteset = note.noteset
		self.locked = self.note.properties.get("locked", False)
		self.resize_edge = None
		self.menu = Gtk.Menu()
		self.populate_menu()
		with open(os.path.join(self.path, "style.css"), encoding="utf-8") as css_file:
			self.css_template = Template(css_file.read())
		self.css = Gtk.CssProvider()
		self.build_note()

	def build_note(self):
		self.builder = Gtk.Builder()
		GObject.type_register(GtkSource.View)
		self.builder.add_from_file(os.path.join(self.path, "StickyNotes.ui"))
		self.builder.connect_signals(self)
		self.winMain = self.builder.get_object("MainWindow")
		widgets = [
			"txtNote", "bAdd", "imgAdd", "bLock", "imgLock", "imgUnlock",
			"imgClose", "imgDropdown", "bClose", "movebox1", "movebox2",
			"bBold", "bItalic", "bUnderline", "bStrike", "bList",
		]
		for w in widgets:
			setattr(self, w, self.builder.get_object(w))
		self.style_contexts = [self.winMain.get_style_context(), self.txtNote.get_style_context()]
		self.winMain.set_resizable(True)
		self.winMain.set_size_request(140, 120)
		self.txtNote.set_size_request(1, 1)
		self.winMain.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
		self.winMain.connect("motion-notify-event", self.on_motion_notify)
		self.winMain.connect("button-press-event", self.on_button_press)
		self.winMain.connect("button-release-event", self.on_button_release)
		self.update_style()
		self.update_font()
		Gtk.Settings.get_default().props.gtk_button_images = True
		self.bbody = GtkSource.Buffer()
		self.bbody.begin_not_undoable_action()
		self.bbody.set_text(self.note.body)
		self.bbody.set_highlight_matching_brackets(False)
		self.bbody.end_not_undoable_action()
		self.txtNote.set_buffer(self.bbody)
		self.winMain.move(*self.note.properties.get("position", (10, 10)))
		self.winMain.resize(*self.note.properties.get("size", (360, 300)))
		self.winMain.set_skip_pager_hint(True)
		self.winMain.show_all()
		self.set_locked_state(self.locked)
		self.winMain.set_keep_above(True)
		self.winMain.set_keep_above(False)

	def show(self, widget=None, event=None, reload_from_backend=False):
		if not reload_from_backend:
			self.update_note()
		else:
			self.populate_menu()
		self.winMain.destroy()
		self.build_note()

	def hide(self, *args):
		self.winMain.hide()

	def on_motion_notify(self, widget, event):
		x, y = event.x, event.y
		w, h = self.winMain.get_size()
		edge = None
		if x < 10 and y < 10:
			edge, cursor = Gdk.WindowEdge.NORTH_WEST, Gdk.CursorType.TOP_LEFT_CORNER
		elif x > w - 10 and y < 10:
			edge, cursor = Gdk.WindowEdge.NORTH_EAST, Gdk.CursorType.TOP_RIGHT_CORNER
		elif x < 10 and y > h - 10:
			edge, cursor = Gdk.WindowEdge.SOUTH_WEST, Gdk.CursorType.BOTTOM_LEFT_CORNER
		elif x > w - 10 and y > h - 10:
			edge, cursor = Gdk.WindowEdge.SOUTH_EAST, Gdk.CursorType.BOTTOM_RIGHT_CORNER
		elif x < 10:
			edge, cursor = Gdk.WindowEdge.WEST, Gdk.CursorType.LEFT_SIDE
		elif x > w - 10:
			edge, cursor = Gdk.WindowEdge.EAST, Gdk.CursorType.RIGHT_SIDE
		elif y < 10:
			edge, cursor = Gdk.WindowEdge.NORTH, Gdk.CursorType.TOP_SIDE
		elif y > h - 10:
			edge, cursor = Gdk.WindowEdge.SOUTH, Gdk.CursorType.BOTTOM_SIDE
		else:
			cursor = Gdk.CursorType.ARROW
		self.winMain.get_window().set_cursor(Gdk.Cursor.new_for_display(self.winMain.get_display(), cursor))
		self.resize_edge = edge

	def on_button_press(self, widget, event):
		if event.button == Gdk.BUTTON_PRIMARY and self.resize_edge:
			self.winMain.begin_resize_drag(self.resize_edge, event.button, event.x_root, event.y_root, event.time)

	def on_button_release(self, widget, event):
		self.resize_edge = None

	def update_note(self):
		self.note.update(self.bbody.get_text(self.bbody.get_start_iter(), self.bbody.get_end_iter(), True))

	def move(self, widget, event):
		self.winMain.begin_move_drag(event.button, event.x_root, event.y_root, event.get_time())
		return False

	def properties(self):
		prop = {"position": self.winMain.get_position(), "size": self.winMain.get_size(), "locked": self.locked}
		if not self.winMain.get_visible():
			prop["position"] = self.note.properties.get("position", (10, 10))
			prop["size"] = self.note.properties.get("size", (360, 300))
		return prop

	def update_font(self):
		self.txtNote.override_font(None)
		font = Pango.FontDescription.from_string(self.note.cat_prop("font"))
		self.txtNote.override_font(font)

	def update_style(self):
		self.update_button_color()
		css_string = self.css_template.substitute(**self.css_data()).encode("ascii", "replace")
		self.css.load_from_data(css_string)
		for context in self.style_contexts:
			context.add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

	def update_button_color(self):
		h, s, v = self.note.cat_prop("bgcolor_hsv")
		thresh_sat = 1.05 - 1.7 * ((v - 1) ** 2)
		suffix = "-dark" if s >= thresh_sat else ""
		iconfiles = {"imgAdd": "add", "imgClose": "close", "imgDropdown": "menu", "imgLock": "lock", "imgUnlock": "unlock"}
		for img, filename in iconfiles.items():
			getattr(self, img).set_from_file(os.path.join(os.path.dirname(__file__), "..", "Icons/" + filename + suffix + ".png"))

	def css_data(self):
		rgb_to_hex = lambda x: "#" + "".join(["{:02x}".format(int(255 * a)) for a in x])
		hsv_to_hex = lambda x: rgb_to_hex(colorsys.hsv_to_rgb(*x))
		return {"bgcolor_hex": hsv_to_hex(self.note.cat_prop("bgcolor_hsv")), "text_color": rgb_to_hex(self.note.cat_prop("textcolor"))}

	def populate_menu(self):
		def _delete_menu_item(item, *args):
			self.menu.remove(item)
		self.menu.foreach(_delete_menu_item, None)
		aot = Gtk.CheckMenuItem.new_with_label(_("Always on top"))
		aot.connect("toggled", self.malways_on_top_toggled)
		self.menu.append(aot)
		aot.show()
		mset = Gtk.MenuItem(_("Settings"))
		mset.connect("activate", self.noteset.indicator.show_settings)
		self.menu.append(mset)
		mset.show()
		sep = Gtk.SeparatorMenuItem()
		self.menu.append(sep)
		sep.show()
		catgroup = []
		mcats = Gtk.RadioMenuItem.new_with_label(catgroup, _("Categories:"))
		self.menu.append(mcats)
		mcats.set_sensitive(False)
		catgroup = mcats.get_group()
		mcats.show()
		for cid, cdata in self.noteset.categories.items():
			mitem = Gtk.RadioMenuItem.new_with_label(catgroup, cdata.get("name", _("New Category")))
			catgroup = mitem.get_group()
			if cid == self.note.category:
				mitem.set_active(True)
			mitem.connect("activate", self.set_category, cid)
			self.menu.append(mitem)
			mitem.show()

	def malways_on_top_toggled(self, widget, *args):
		self.winMain.set_keep_above(widget.get_active())

	def save(self, *args):
		self.note.noteset.save()
		return False

	def add(self, *args):
		new_note = self.note.noteset.new()
		new_note.gui.set_category(None, self.note.category)
		new_note.gui.populate_menu()
		w, h = self.note.properties.get("position", (10, 10))
		h += self.winMain.get_allocation().height + 10
		new_note.gui.winMain.move(w, h)
		return False

	def delete(self, *args):
		winConfirm = Gtk.MessageDialog(self.winMain, None, Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE, _("Are you sure you want to delete this note?"))
		winConfirm.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_DELETE, Gtk.ResponseType.ACCEPT)
		confirm = winConfirm.run()
		winConfirm.destroy()
		if confirm == Gtk.ResponseType.ACCEPT:
			self.note.delete()
			self.winMain.destroy()
			return False
		return True

	def popup_menu(self, button, *args):
		self.menu.popup(None, None, None, None, Gdk.BUTTON_PRIMARY, Gtk.get_current_event_time())

	def set_category(self, widget, cat):
		if not cat in self.noteset.categories:
			raise KeyError("No such category")
		self.note.category = cat
		self.update_style()
		self.update_font()

	def _format_then_save(self, formatter):
		if self.locked:
			return False
		formatter(self.bbody)
		self.update_note()
		self.save()
		self.txtNote.grab_focus()
		return False

	def bold_clicked(self, *args):
		return self._format_then_save(lambda b: wrap_selection(b, "**", "**", "bold"))

	def italic_clicked(self, *args):
		return self._format_then_save(lambda b: wrap_selection(b, "*", "*", "italic"))

	def underline_clicked(self, *args):
		return self._format_then_save(lambda b: wrap_selection(b, "<u>", "</u>", "underline"))

	def strike_clicked(self, *args):
		return self._format_then_save(lambda b: wrap_selection(b, "~~", "~~", "strike"))

	def list_clicked(self, *args):
		return self._format_then_save(lambda b: prefix_current_lines(b, "- "))

	def set_locked_state(self, locked):
		self.locked = locked
		self.txtNote.set_editable(not self.locked)
		self.txtNote.set_cursor_visible(not self.locked)
		self.bLock.set_image({True: self.imgLock, False: self.imgUnlock}[self.locked])
		self.bLock.set_tooltip_text({True: _("Unlock"), False: _("Lock")}[self.locked])

	def lock_clicked(self, *args):
		self.set_locked_state(not self.locked)

	def focus_out(self, *args):
		self.save(*args)


def show_about_dialog():
	glade_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', "GlobalDialogs.ui"))
	builder = Gtk.Builder()
	builder.add_from_file(glade_file)
	winAbout = builder.get_object("AboutWindow")
	ret = winAbout.run()
	winAbout.destroy()
	return ret


class SettingsCategory:
	def __init__(self, settingsdialog, cat):
		self.settingsdialog = settingsdialog
		self.noteset = settingsdialog.noteset
		self.cat = cat
		self.builder = Gtk.Builder()
		self.path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
		self.builder.add_objects_from_file(os.path.join(self.path, "SettingsCategory.ui"), ["catExpander"])
		self.builder.connect_signals(self)
		widgets = ["catExpander", "lExp", "cbBG", "cbText", "eName", "confirmDelete", "fbFont"]
		for w in widgets:
			setattr(self, w, self.builder.get_object(w))
		name = self.noteset.categories[cat].get("name", _("New Category"))
		self.eName.set_text(name)
		self.refresh_title()
		self.cbBG.set_rgba(Gdk.RGBA(*colorsys.hsv_to_rgb(*self.noteset.get_category_property(cat, "bgcolor_hsv")), alpha=1))
		self.cbText.set_rgba(Gdk.RGBA(*self.noteset.get_category_property(cat, "textcolor"), alpha=1))
		fontname = self.noteset.get_category_property(cat, "font")
		if not fontname:
			fontname = self.settingsdialog.wSettings.get_style_context().get_font(Gtk.StateFlags.NORMAL).to_string()
		self.fbFont.set_font(fontname)

	def refresh_title(self, *args):
		name = self.noteset.categories[self.cat].get("name", _("New Category"))
		if self.noteset.properties.get("default_cat", "") == self.cat:
			name += " (" + _("Default Category") + ")"
		self.lExp.set_text(name)

	def delete_cat(self, *args):
		winConfirm = Gtk.MessageDialog(self.settingsdialog.wSettings, None, Gtk.MessageType.QUESTION, Gtk.ButtonsType.NONE, _("Are you sure you want to delete this category?"))
		winConfirm.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT, Gtk.STOCK_DELETE, Gtk.ResponseType.ACCEPT)
		confirm = winConfirm.run()
		winConfirm.destroy()
		if confirm == Gtk.ResponseType.ACCEPT:
			self.settingsdialog.delete_category(self.cat)

	def make_default(self, *args):
		self.noteset.properties["default_cat"] = self.cat
		self.settingsdialog.refresh_category_titles()
		for note in self.noteset.notes:
			note.gui.update_style()
			note.gui.update_font()

	def eName_changed(self, *args):
		self.noteset.categories[self.cat]["name"] = self.eName.get_text()
		self.refresh_title()
		for note in self.noteset.notes:
			note.gui.populate_menu()

	def update_bg(self, *args):
		try:
			rgba = self.cbBG.get_rgba()
		except TypeError:
			rgba = Gdk.RGBA()
			self.cbBG.get_rgba(rgba)
		hsv = colorsys.rgb_to_hsv(rgba.red, rgba.green, rgba.blue)
		self.noteset.categories[self.cat]["bgcolor_hsv"] = hsv
		for note in self.noteset.notes:
			note.gui.update_style()
		load_global_css()

	def update_textcolor(self, *args):
		try:
			rgba = self.cbText.get_rgba()
		except TypeError:
			rgba = Gdk.RGBA()
			self.cbText.get_rgba(rgba)
		self.noteset.categories[self.cat]["textcolor"] = [rgba.red, rgba.green, rgba.blue]
		for note in self.noteset.notes:
			note.gui.update_style()

	def update_font(self, *args):
		self.noteset.categories[self.cat]["font"] = self.fbFont.get_font_name()
		for note in self.noteset.notes:
			note.gui.update_font()


class SettingsDialog:
	def __init__(self, noteset):
		self.noteset = noteset
		self.categories = {}
		self.path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
		self.builder = Gtk.Builder()
		self.builder.add_from_file(os.path.join(self.path, "GlobalDialogs.ui"))
		self.builder.connect_signals(self)
		widgets = ["wSettings", "boxCategories"]
		for w in widgets:
			setattr(self, w, self.builder.get_object(w))
		for c in self.noteset.categories:
			self.add_category_widgets(c)
		self.wSettings.run()
		self.wSettings.destroy()

	def add_category_widgets(self, cat):
		self.categories[cat] = SettingsCategory(self, cat)
		self.boxCategories.pack_start(self.categories[cat].catExpander, False, False, 0)

	def new_category(self, *args):
		cid = str(uuid.uuid4())
		self.noteset.categories[cid] = {}
		self.add_category_widgets(cid)

	def delete_category(self, cat):
		del self.noteset.categories[cat]
		self.categories[cat].catExpander.destroy()
		del self.categories[cat]
		for note in self.noteset.notes:
			note.gui.populate_menu()
			note.gui.update_style()
			note.gui.update_font()

	def refresh_category_titles(self):
		for cid, catsettings in self.categories.items():
			catsettings.refresh_title()
