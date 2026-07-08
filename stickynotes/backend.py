# Copyright © 2012-2015 Umang Varma <umang.me@gmail.com>
#
# This file is part of indicator-stickynotes.
#
# indicator-stickynotes is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.

from datetime import datetime
import json
import os
import shutil
import uuid
from os.path import expanduser

from stickynotes.info import FALLBACK_PROPERTIES


NOTE_BODY_FILE = "note.md"
NOTE_META_FILE = "meta.json"
SETTINGS_FILE_NAME = "settings.json"
CATEGORIES_FILE_NAME = "categories.json"


class Note:
    def __init__(self, content=None, gui_class=None, noteset=None,
            category=None):
        self.gui_class = gui_class
        self.noteset = noteset
        content = content or {}
        self.uuid = content.get('uuid') or str(uuid.uuid4())
        self.body = content.get('body', '')
        self.properties = content.get("properties", {})
        self.category = category or content.get("cat", "")
        if self.noteset and not self.category in self.noteset.categories:
            self.category = ""
        last_modified = content.get('last_modified') or content.get('updated_at')
        if last_modified:
            self.last_modified = self._parse_datetime(last_modified)
        else:
            self.last_modified = datetime.now()
        self.created_at = self._parse_datetime(
            content.get('created_at'), fallback=self.last_modified)
        # Don't create GUI until show is called
        self.gui = None

    @staticmethod
    def _parse_datetime(value, fallback=None):
        if not value:
            return fallback or datetime.now()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        return fallback or datetime.now()

    def extract(self):
        if not self.uuid:
            self.uuid = str(uuid.uuid4())
        if self.gui != None:
            self.gui.update_note()
            self.properties = self.gui.properties()
        return {"uuid": self.uuid, "body": self.body,
                "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
                "last_modified": self.last_modified.strftime(
                    "%Y-%m-%dT%H:%M:%S"), "properties": self.properties,
                "cat": self.category}

    def meta(self):
        data = self.extract().copy()
        data.pop("body", None)
        return data

    def update(self, body=None):
        if not body == None:
            self.body = body
            self.last_modified = datetime.now()

    def delete(self):
        self.noteset.notes.remove(self)
        self.noteset.delete_note_files(self)
        self.noteset.save()
        del self

    def show(self, *args, **kwargs):
        # If GUI has not been created, create it now
        if self.gui == None:
            self.gui = self.gui_class(note=self)
        else:
            self.gui.show(*args, **kwargs)

    def hide(self):
        if self.gui != None:
            self.gui.hide()

    def set_locked_state(self, locked):
        # if gui hasn't been initialized, just change the property
        if self.gui == None:
            self.properties["locked"] = locked
        else:
            self.gui.set_locked_state(locked)

    def cat_prop(self, prop):
        """Gets a property of the note's category"""
        return self.noteset.get_category_property(self.category, prop)


class NoteSet:
    def __init__(self, gui_class, data_file, indicator):
        self.notes = []
        self.properties = {}
        self.categories = {}
        self.gui_class = gui_class
        self.data_file = data_file
        self.indicator = indicator

    @property
    def data_path(self):
        return expanduser(self.data_file)

    @property
    def notes_dir(self):
        return os.path.join(self.data_path, "notes")

    @property
    def settings_path(self):
        return os.path.join(self.data_path, SETTINGS_FILE_NAME)

    @property
    def categories_path(self):
        return os.path.join(self.data_path, CATEGORIES_FILE_NAME)

    def _loads_updater(self, dnoteset):
        """Parses old versions of the Notes structure and updates them"""
        return dnoteset

    def loads(self, snoteset):
        """Loads notes into their respective objects from the legacy JSON form."""
        notes = self._loads_updater(json.loads(snoteset or '{}'))
        self.properties = notes.get("properties", {})
        self.categories = notes.get("categories", {})
        self.notes = [Note(note, gui_class=self.gui_class, noteset=self)
                for note in notes.get("notes", [])]

    def dumps(self):
        """Export notes in the legacy single-file JSON form."""
        return json.dumps({"notes": [x.extract() for x in self.notes],
            "properties": self.properties, "categories": self.categories},
            ensure_ascii=False, indent=2)

    def _ensure_storage_dir(self):
        data_path = self.data_path
        if os.path.isfile(data_path):
            backup = data_path + ".legacy-backup"
            if not os.path.exists(backup):
                shutil.copy2(data_path, backup)
            os.remove(data_path)
        os.makedirs(self.notes_dir, exist_ok=True)

    def _write_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode='w', encoding='utf-8') as fsock:
            json.dump(data, fsock, ensure_ascii=False, indent=2)
            fsock.write("\n")

    def _read_json(self, path, fallback):
        if not os.path.exists(path):
            return fallback
        with open(path, encoding='utf-8') as fsock:
            return json.load(fsock)

    def _note_path(self, note):
        return os.path.join(self.notes_dir, note.uuid)

    def _save_note(self, note):
        note_dir = self._note_path(note)
        os.makedirs(note_dir, exist_ok=True)
        with open(os.path.join(note_dir, NOTE_BODY_FILE), mode='w',
                encoding='utf-8') as fsock:
            fsock.write(note.body or '')
        self._write_json(os.path.join(note_dir, NOTE_META_FILE), note.meta())

    def delete_note_files(self, note):
        shutil.rmtree(self._note_path(note), ignore_errors=True)

    def save(self, path=''):
        # Explicit paths are treated as export targets for backwards compatibility.
        if path:
            with open(path, mode='w', encoding='utf-8') as fsock:
                fsock.write(self.dumps())
            return

        self._ensure_storage_dir()
        self._write_json(self.settings_path, self.properties)
        self._write_json(self.categories_path, self.categories)

        active_ids = set()
        for note in self.notes:
            active_ids.add(note.uuid)
            self._save_note(note)

        # Remove orphaned note directories from deleted notes.
        if os.path.isdir(self.notes_dir):
            for name in os.listdir(self.notes_dir):
                note_path = os.path.join(self.notes_dir, name)
                if os.path.isdir(note_path) and name not in active_ids:
                    shutil.rmtree(note_path, ignore_errors=True)

    def _open_directory_storage(self, path):
        self.properties = self._read_json(
            os.path.join(path, SETTINGS_FILE_NAME), {})
        self.categories = self._read_json(
            os.path.join(path, CATEGORIES_FILE_NAME), {})
        self.notes = []

        notes_dir = os.path.join(path, "notes")
        if not os.path.isdir(notes_dir):
            return

        for note_id in sorted(os.listdir(notes_dir)):
            note_path = os.path.join(notes_dir, note_id)
            if not os.path.isdir(note_path):
                continue
            meta_path = os.path.join(note_path, NOTE_META_FILE)
            body_path = os.path.join(note_path, NOTE_BODY_FILE)
            meta = self._read_json(meta_path, {})
            meta.setdefault("uuid", note_id)
            if os.path.exists(body_path):
                with open(body_path, encoding='utf-8') as fsock:
                    meta["body"] = fsock.read()
            self.notes.append(Note(meta, gui_class=self.gui_class,
                    noteset=self))

    def open(self, path=''):
        data_path = expanduser(path or self.data_file)
        if os.path.isdir(data_path):
            self._open_directory_storage(data_path)
            return

        with open(data_path, encoding='utf-8') as fsock:
            self.loads(fsock.read())
        # Migrate legacy single-file JSON to the new directory layout.
        if not path:
            self.save()

    def load_fresh(self):
        """Load empty data"""
        self.loads('{}')
        self.new()

    def merge(self, data):
        """Update notes based on imported legacy JSON data"""
        jdata = self._loads_updater(json.loads(data))
        self.hideall()
        # update categories
        if "categories" in jdata:
            self.categories.update(jdata["categories"])
        # make a dictionary of notes so we can modify existing notes
        dnotes = {n.uuid: n for n in self.notes}
        for newnote in jdata.get("notes", []):
            if "uuid" in newnote and newnote["uuid"] in dnotes:
                # Update notes that are already in the noteset
                orignote = dnotes[newnote["uuid"]]
                if "body" in newnote:
                    orignote.body = newnote["body"]
                if "properties" in newnote:
                    orignote.properties = newnote["properties"]
                if "cat" in newnote:
                    orignote.category = newnote["cat"]
            else:
                # otherwise create a new note
                if "uuid" in newnote:
                    note_uuid = newnote["uuid"]
                else:
                    note_uuid = str(uuid.uuid4())
                newnote["uuid"] = note_uuid
                dnotes[note_uuid] = Note(newnote, gui_class=self.gui_class,
                        noteset=self)
        # copy notes over from dictionary to list
        self.notes = list(dnotes.values())
        self.save()
        self.showall(reload_from_backend=True)

    def new(self):
        """Creates a new note and adds it to the note set"""
        note = Note(gui_class=self.gui_class, noteset=self,
                category=self.properties.get("default_cat", ""))
        self.notes.append(note)
        note.show()
        self.save()
        return note

    def showall(self, *args, **kwargs):
        for note in self.notes:
            note.show(*args, **kwargs)
        self.properties["all_visible"] = True

    def hideall(self, *args):
        self.save()
        for note in self.notes:
            note.hide(*args)
        self.properties["all_visible"] = False

    def get_category_property(self, cat, prop):
        """Get a property of a category or the default"""
        if ((not cat) or (not cat in self.categories)) and \
                self.properties.get("default_cat", None):
            cat = self.properties["default_cat"]
        cat_data = self.categories.get(cat, {})
        if prop in cat_data:
            return cat_data[prop]
        # Otherwise, use fallback categories
        if prop in FALLBACK_PROPERTIES:
            return FALLBACK_PROPERTIES[prop]
        else:
            raise ValueError("Unknown property")


class dGUI:
    """Dummy GUI"""
    def __init__(self, *args, **kwargs):
        pass
    def show(self):
        pass
    def hide(self):
        pass
    def update_note(self):
        pass
    def properties(self):
        return None
