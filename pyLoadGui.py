#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License,
    or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    See the GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, see <http://www.gnu.org/licenses/>.

    @author: mkaay
    @version: v0.4.0
"""

import sys

from time import sleep

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from uuid import uuid4 as uuid
import re
import gettext
from xmlrpclib import Binary
from os.path import abspath
from os.path import join
from os.path import basename

from module import InitHomeDir
from module.gui.ConnectionManager import *
from module.gui.connector import Connector
from module.gui.MainWindow import *
from module.gui.Queue import *
from module.gui.Collector import *
from module.gui.XMLParser import *
from module.gui.CoreConfigParser import ConfigParser

try:
    import pynotify
except ImportError:
    pass

class main(QObject):
    def __init__(self):
        """
            main setup
        """
        QObject.__init__(self)
        self.app = QApplication(sys.argv)
        self.path = pypath
        self.homedir = abspath("")

        self.configdir = ""

        self.init(True)

    def init(self, first=False):
        """
            set main things up
        """
        self.parser = XMLParser(join(self.configdir, "gui.xml"), join(self.path, "module", "config", "gui_default.xml"))
        lang = self.parser.xml.elementsByTagName("language").item(0).toElement().text()
        if not lang:
            parser = XMLParser(join(self.path, "module", "config", "gui_default.xml"))
            lang = parser.xml.elementsByTagName("language").item(0).toElement().text()

        translation = gettext.translation("pyLoadGui", join(pypath, "locale"), languages=[str(lang)])
        try:
            translation.install(unicode=(True if sys.stdout.encoding.lower().startswith("utf") else False))
        except:
            translation.install(unicode=False)

        self.connector = Connector()
        self.mainWindow = MainWindow(self.connector)
        self.connWindow = ConnectionManager()
        self.mainloop = self.Loop(self)
        self.connectSignals()

        self.checkClipboard = False
        default = self.refreshConnections()
        self.connData = None
        self.captchaProcessing = False

        if True:
            self.tray = TrayIcon()
            self.tray.show()
            self.notification = Notification(self.tray)
            self.connect(self, SIGNAL("showMessage"), self.notification.showMessage)
            self.connect(self.tray.exitAction, SIGNAL("triggered()"), self.app.quit)
            self.connect(self.tray.showAction, SIGNAL("toggled(bool)"), self.mainWindow.setVisible)
            self.connect(self.mainWindow, SIGNAL("hidden"), self.tray.mainWindowHidden)

        if not first:
            self.connWindow.show()
        else:
            self.connWindow.edit.setData(default)
            data = self.connWindow.edit.getData()
            self.slotConnect(data)

    def startMain(self):
        """
            start all refresh threads and show main window
        """
        if not self.connector.canConnect():
            self.init()
            return
        self.connector.start()
        self.connect(self.connector, SIGNAL("connectionLost"), sys.exit)
        sleep(1)
        self.restoreMainWindow()
        self.mainWindow.show()
        self.initQueue()
        self.initPackageCollector()
        self.mainloop.start()
        self.clipboard = self.app.clipboard()
        self.connect(self.clipboard, SIGNAL('dataChanged()'), self.slotClipboardChange)
        self.mainWindow.actions["clipboard"].setChecked(self.checkClipboard)

        self.mainWindow.tabs["settings"]["w"].setConnector(self.connector)
        self.mainWindow.tabs["settings"]["w"].loadConfig()
        self.tray.showAction.setDisabled(False)

    def stopMain(self):
        """
            stop all refresh threads and hide main window
        """
        self.tray.showAction.setDisabled(True)
        self.disconnect(self.clipboard, SIGNAL('dataChanged()'), self.slotClipboardChange)
        self.disconnect(self.connector, SIGNAL("connectionLost"), sys.exit)
        self.mainloop.stop()
        self.connector.stop()
        self.mainWindow.saveWindow()
        self.mainWindow.hide()
        self.queue.stop()
        self.connector.wait()

    def connectSignals(self):
        """
            signal and slot stuff, yay!
        """
        self.connect(self.connector, SIGNAL("error_box"), self.slotErrorBox)
        self.connect(self.connWindow, SIGNAL("saveConnection"), self.slotSaveConnection)
        self.connect(self.connWindow, SIGNAL("removeConnection"), self.slotRemoveConnection)
        self.connect(self.connWindow, SIGNAL("connect"), self.slotConnect)
        self.connect(self.mainWindow, SIGNAL("connector"), self.slotShowConnector)
        self.connect(self.mainWindow, SIGNAL("addPackage"), self.slotAddPackage)
        self.connect(self.mainWindow, SIGNAL("setDownloadStatus"), self.slotSetDownloadStatus)
        self.connect(self.mainWindow, SIGNAL("saveMainWindow"), self.slotSaveMainWindow)
        self.connect(self.mainWindow, SIGNAL("pushPackageToQueue"), self.slotPushPackageToQueue)
        self.connect(self.mainWindow, SIGNAL("restartDownload"), self.slotRestartDownload)
        self.connect(self.mainWindow, SIGNAL("removeDownload"), self.slotRemoveDownload)
        self.connect(self.mainWindow, SIGNAL("abortDownload"), self.slotAbortDownload)
        self.connect(self.mainWindow, SIGNAL("addContainer"), self.slotAddContainer)
        self.connect(self.mainWindow, SIGNAL("stopAllDownloads"), self.slotStopAllDownloads)
        self.connect(self.mainWindow, SIGNAL("setClipboardStatus"), self.slotSetClipboardStatus)
        self.connect(self.mainWindow, SIGNAL("changePackageName"), self.slotChangePackageName)
        self.connect(self.mainWindow, SIGNAL("pullOutPackage"), self.slotPullOutPackage)
        self.connect(self.mainWindow, SIGNAL("setPriority"), self.slotSetPriority)
        self.connect(self.mainWindow, SIGNAL("reloadAccounts"), self.slotReloadAccounts)

        self.connect(self.mainWindow, SIGNAL("quit"), self.quit)
        self.connect(self.mainWindow.captchaDock, SIGNAL("done"), self.slotCaptchaDone)

    def slotShowConnector(self):
        """
            emitted from main window (menu)
            hide the main window and show connection manager
            (to switch to other core)
        """
        self.stopMain()
        self.init()

    def quit(self):
        """
            quit gui
        """
        self.app.quit()

    def loop(self):
        """
            start application loop
        """
        sys.exit(self.app.exec_())

    def slotErrorBox(self, msg):
        """
            display a nice error box
        """
        msgb = QMessageBox(QMessageBox.Warning, "Error", msg)
        msgb.exec_()

    def initPackageCollector(self):
        """
            init the package collector view
            * columns
            * selection
            * refresh thread
            * drag'n'drop
        """
        view = self.mainWindow.tabs["collector"]["package_view"]
        view.setSelectionBehavior(QAbstractItemView.SelectRows)
        view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        def dropEvent(klass, event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            view = event.source()
            if view == klass:
                items = view.selectedItems()
                for item in items:
                    if not hasattr(item.parent(), "getPackData"):
                        continue
                    target = view.itemAt(event.pos())
                    if not hasattr(target, "getPackData"):
                        target = target.parent()
                    klass.emit(SIGNAL("droppedToPack"), target.getPackData()["id"], item.getFileData()["id"])
                event.ignore()
                return
            items = view.selectedItems()
            for item in items:
                row = view.indexOfTopLevelItem(item)
                view.takeTopLevelItem(row)
        def dragEvent(klass, event):
            view = event.source()
            #dragOkay = False
            #items = view.selectedItems()
            #for item in items:
            #    if hasattr(item, "_data"):
            #        if item._data["id"] == "fixed" or item.parent()._data["id"] == "fixed":
            #            dragOkay = True
            #    else:
            #        dragOkay = True
            #if dragOkay:
            event.accept()
            #else:
            #    event.ignore()
        view.dropEvent = dropEvent
        view.dragEnterEvent = dragEvent
        view.setDragEnabled(True)
        view.setDragDropMode(QAbstractItemView.DragDrop)
        view.setDropIndicatorShown(True)
        view.setDragDropOverwriteMode(True)
        view.connect(view, SIGNAL("droppedToPack"), self.slotAddFileToPackage)
        #self.packageCollector = PackageCollector(view, self.connector)
        self.packageCollector = view.model()

    def initQueue(self):
        """
            init the queue view
            * columns
            * progressbar
        """
        view = self.mainWindow.tabs["queue"]["view"]
        view.setSelectionBehavior(QAbstractItemView.SelectRows)
        view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.queue = view.model()
        self.queue.start()

    def refreshServerStatus(self):
        """
            refresh server status and overall speed in the status bar
        """
        status = self.connector.getServerStatus()
        if status["pause"]:
            status["status"] = _("Paused")
        else:
            status["status"] = _("Running")
        status["speed"] = int(status["speed"])
        text = _("Status: %(status)s | Speed: %(speed)s kb/s") % status
        self.mainWindow.actions["toggle_status"].setChecked(not status["pause"])
        self.mainWindow.serverStatus.setText(text)

    def refreshLog(self):
        """
            update log window
        """
        offset = self.mainWindow.tabs["log"]["text"].logOffset
        lines = self.connector.getLog(offset)
        if not lines:
            return
        self.mainWindow.tabs["log"]["text"].logOffset += len(lines)
        for line in lines:
            self.mainWindow.tabs["log"]["text"].emit(SIGNAL("append(QString)"), line.strip("\n"))
        cursor = self.mainWindow.tabs["log"]["text"].textCursor()
        cursor.movePosition(QTextCursor.End, QTextCursor.MoveAnchor)
        self.mainWindow.tabs["log"]["text"].setTextCursor(cursor)

    def getConnections(self):
        """
            parse all connections in the config file
        """
        connectionsNode = self.parser.xml.elementsByTagName("connections").item(0)
        if connectionsNode.isNull():
            raise Exception("null")
        connections = self.parser.parseNode(connectionsNode)
        ret = []
        for conn in connections:
            data = {}
            data["type"] = conn.attribute("type", "remote")
            data["default"] = conn.attribute("default", "False")
            data["id"] = conn.attribute("id", uuid().hex)
            if data["default"] == "True":
                data["default"] = True
            else:
                data["default"] = False
            subs = self.parser.parseNode(conn, "dict")
            if not subs.has_key("name"):
                data["name"] = _("Unnamed")
            else:
                data["name"] = subs["name"].text()
            if data["type"] == "remote":
                if not subs.has_key("server"):
                    continue
                else:
                    data["host"] = subs["server"].text()
                    data["ssl"] = subs["server"].attribute("ssl", "False")
                    if data["ssl"] == "True":
                        data["ssl"] = True
                    else:
                        data["ssl"] = False
                    data["user"] = subs["server"].attribute("user", "admin")
                    data["port"] = int(subs["server"].attribute("port", "7227"))
                    data["password"] = subs["server"].attribute("password", "")
            ret.append(data)
        return ret

    def slotSaveConnection(self, data):
        """
            save connection to config file
        """
        connectionsNode = self.parser.xml.elementsByTagName("connections").item(0)
        if connectionsNode.isNull():
            raise Exception("null")
        connections = self.parser.parseNode(connectionsNode)
        connNode = self.parser.xml.createElement("connection")
        connNode.setAttribute("default", str(data["default"]))
        connNode.setAttribute("type", data["type"])
        connNode.setAttribute("id", data["id"])
        nameNode = self.parser.xml.createElement("name")
        nameText = self.parser.xml.createTextNode(data["name"])
        nameNode.appendChild(nameText)
        connNode.appendChild(nameNode)
        if data["type"] == "remote":
            serverNode = self.parser.xml.createElement("server")
            serverNode.setAttribute("ssl", data["ssl"])
            serverNode.setAttribute("user", data["user"])
            serverNode.setAttribute("port", data["port"])
            serverNode.setAttribute("password", data["password"])
            hostText = self.parser.xml.createTextNode(data["host"])
            serverNode.appendChild(hostText)
            connNode.appendChild(serverNode)
        found = False
        for c in connections:
            cid = c.attribute("id", "None")
            if str(cid) == str(data["id"]):
                found = c
                break
        if found:
            connectionsNode.replaceChild(connNode, found)
        else:
            connectionsNode.appendChild(connNode)
        self.parser.saveData()
        self.refreshConnections()

    def slotRemoveConnection(self, data):
        """
            remove connection from config file
        """
        connectionsNode = self.parser.xml.elementsByTagName("connections").item(0)
        if connectionsNode.isNull():
            raise Exception("null")
        connections = self.parser.parseNode(connectionsNode)
        found = False
        for c in connections:
            cid = c.attribute("id", "None")
            if str(cid) == str(data["id"]):
                found = c
                break
        if found:
            connectionsNode.removeChild(found)
        self.parser.saveData()
        self.refreshConnections()

    def slotConnect(self, data):
        """
            connect to a core
            if connection is local, parse the core config file for data
            set up connector, show main window
        """
        self.connWindow.hide()
        if not data["type"] == "remote":

            coreparser = ConfigParser(self.configdir)
            if not coreparser.config:
                raise Exception
            #except:
            #    data["port"] = 7227
            #    data["user"] = "admin"
            #    data["password"] = "pwhere"
            #    data["host"] = "127.0.0.1"
            #    data["ssl"] = False

            data["port"] = coreparser.get("remote","port")
            data["user"] = coreparser.get("remote","username")
            data["password"] = coreparser.get("remote","password")
            data["host"] = "127.0.0.1"
            data["ssl"] = coreparser.get("ssl","activated")
        data["ssl"] = "s" if data["ssl"] else ""
        server_url = "http%(ssl)s://%(user)s:%(password)s@%(host)s:%(port)s/" % data
        self.connector.setAddr(str(server_url))
        self.startMain()

    def refreshConnections(self):
        """
            reload connetions and display them
        """
        self.parser.loadData()
        conns = self.getConnections()
        self.connWindow.emit(SIGNAL("setConnections"), conns)
        for conn in conns:
            if conn["default"]:
                return conn
        return None

    def slotSetDownloadStatus(self, status):
        """
            toolbar start/pause slot
        """
        self.connector.setPause(not status)

    def slotAddPackage(self, name, links):
        """
            emitted from main window
            add package to the collector
        """
        self.connector.proxy.add_package(name, links)

    def slotAddFileToPackage(self, pid, fid):
        """
            emitted from collector view after a drop action
        """
        self.connector.addFileToPackage(fid, pid)

    def slotAddContainer(self, path):
        """
            emitted from main window
            add container
        """
        filename = basename(path)
        type = "".join(filename.split(".")[-1])
        fh = open(path, "r")
        content = fh.read()
        fh.close()
        self.connector.proxy.upload_container(filename, Binary(content))

    def slotSaveMainWindow(self, state, geo):
        """
            save the window geometry and toolbar/dock position to config file
        """
        mainWindowNode = self.parser.xml.elementsByTagName("mainWindow").item(0)
        if mainWindowNode.isNull():
            mainWindowNode = self.parser.xml.createElement("mainWindow")
            self.parser.root.appendChild(mainWindowNode)
        stateNode = mainWindowNode.toElement().elementsByTagName("state").item(0)
        geoNode = mainWindowNode.toElement().elementsByTagName("geometry").item(0)
        newStateNode = self.parser.xml.createTextNode(state)
        newGeoNode = self.parser.xml.createTextNode(geo)

        stateNode.removeChild(stateNode.firstChild())
        geoNode.removeChild(geoNode.firstChild())
        stateNode.appendChild(newStateNode)
        geoNode.appendChild(newGeoNode)

        self.parser.saveData()

    def restoreMainWindow(self):
        """
            load and restore main window geometry and toolbar/dock position from config
        """
        mainWindowNode = self.parser.xml.elementsByTagName("mainWindow").item(0)
        if mainWindowNode.isNull():
            return
        nodes = self.parser.parseNode(mainWindowNode, "dict")

        state = str(nodes["state"].text())
        geo = str(nodes["geometry"].text())

        self.mainWindow.restoreWindow(state, geo)
        self.mainWindow.captchaDock.hide()

    def slotPushPackageToQueue(self, id):
        """
            emitted from main window
            push the collector package to queue
        """
        self.connector.proxy.push_package_to_queue(id)

    def slotRestartDownload(self, id, isPack):
        """
            emitted from main window
            restart download
        """
        if isPack:
            self.connector.restartPackage(id)
        else:
            self.connector.restartFile(id)

    def slotRemoveDownload(self, id, isPack):
        """
            emitted from main window
            remove download
        """
        if isPack:
            self.connector.removePackage(id)
        else:
            self.connector.removeFile(id)

    def slotAbortDownload(self, id, isPack):
        """
            emitted from main window
            remove download
        """
        if isPack:
            data = self.connector.proxy.get_package_data(id)
            self.connector.proxy.abort_files(data["links"].keys())
        else:
            self.connector.proxy.abort_files([id])

    def slotStopAllDownloads(self):
        """
            emitted from main window
            stop all running downloads
        """
        self.connector.stopAllDownloads()

    def slotClipboardChange(self):
        """
            called if clipboard changes
        """
        if self.checkClipboard:
            text = self.clipboard.text()
            pattern = re.compile(r"(http|https)://[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,5}(([0-9]{1,5})?/.*)?")
            matches = pattern.finditer(text)
            for match in matches:
                self.slotAddLinks([str(match.group(0))])

    def slotSetClipboardStatus(self, status):
        """
            set clipboard checking
        """
        self.checkClipboard = status

    def slotChangePackageName(self, pid, name):
        """
            package name edit finished
        """
        self.connector.setPackageName(pid, str(name))

    def slotPullOutPackage(self, pid):
        """
            pull package out of the queue
        """
        self.connector.proxy.pull_out_package(pid)

    def slotSetPriority(self, pid, level):
        """
            set package priority
        """
        self.connector.proxy.set_priority(pid, level)

    def checkCaptcha(self):
        if self.connector.captchaWaiting() and self.mainWindow.captchaDock.isFree():
            cid, img, imgType = self.connector.getCaptcha()
            self.mainWindow.captchaDock.emit(SIGNAL("setTask"), cid, str(img), imgType)
            self.mainWindow.show()
        elif not self.mainWindow.captchaDock.isFree():
            status = self.connector.getCaptchaStatus(self.mainWindow.captchaDock.currentID)
            if not (status == "user" or status == "shared-user"):
                self.mainWindow.captchaDock.hide()
                self.mainWindow.captchaDock.processing = False
                self.mainWindow.captchaDock.currentID = None

    def slotCaptchaDone(self, cid, result):
        self.connector.setCaptchaResult(str(cid), str(result))

    def pullEvents(self):
        events = self.connector.getEvents()
        for event in events:
            if event[1] == "queue":
                self.queue.addEvent(event)
                try:
                    if event[0] == "update" and event[2] == "file":
                        info = self.connector.getLinkInfo(event[3])
                        if info["status_type"] == "finished":
                            self.emit(SIGNAL("showMessage"), _("Finished downloading of '%s'") % info["status_filename"])
                        elif info["status_type"] == "downloading":
                            self.emit(SIGNAL("showMessage"), _("Started downloading '%s'") % info["status_filename"])
                        elif info["status_type"] == "failed":
                            self.emit(SIGNAL("showMessage"), _("Failed downloading '%s'!") % info["status_filename"])
                    if event[0] == "insert" and event[2] == "file":
                        info = self.connector.getLinkInfo(event[3])
                        self.emit(SIGNAL("showMessage"), _("Added '%s' to queue") % info["status_filename"])
                except:
                    pass
            elif event[1] == "collector":
                self.packageCollector.addEvent(event)

    def slotReloadAccounts(self):
        self.mainWindow.tabs["accounts"]["view"].model().reloadData()

    class Loop():
        def __init__(self, parent):
            self.parent = parent
            self.timer = QTimer()
            self.timer.connect(self.timer, SIGNAL("timeout()"), self.update)

        def start(self):
            self.update()
            self.timer.start(1000)

        def update(self):
            """
                methods to call
            """
            self.parent.refreshServerStatus()
            self.parent.refreshLog()
            self.parent.checkCaptcha()
            self.parent.pullEvents()

        def stop(self):
            self.timer.stop()


class TrayIcon(QSystemTrayIcon):
    def __init__(self):
        QSystemTrayIcon.__init__(self, QIcon(join(pypath, "icons", "logo.png")))
        self.contextMenu = QMenu()
        self.showAction = QAction(_("Show"), self.contextMenu)
        self.showAction.setCheckable(True)
        self.showAction.setChecked(True)
        self.showAction.setDisabled(True)
        self.contextMenu.addAction(self.showAction)
        self.exitAction = QAction(QIcon(join(pypath, "icons", "close.png")), _("Exit"), self.contextMenu)
        self.contextMenu.addAction(self.exitAction)
        self.setContextMenu(self.contextMenu)

        self.connect(self, SIGNAL("activated(QSystemTrayIcon::ActivationReason)"), self.doubleClicked)

    def mainWindowHidden(self):
        self.showAction.setChecked(False)

    def doubleClicked(self, reason):
        if self.showAction.isEnabled():
            if reason == QSystemTrayIcon.DoubleClick:
                self.showAction.toggle()

class Notification(QObject):
    def __init__(self, tray):
        QObject.__init__(self)
        self.tray = tray
        self.usePynotify = False

        try:
            self.usePynotify = pynotify.init("icon-summary-body")
        except:
            pass

    def showMessage(self, body):
        if self.usePynotify:
            n = pynotify.Notification("pyload", body, join(pypath, "icons", "logo.png"))
            try:
                n.set_hint_string("x-canonical-append", "")
            except:
                pass
            n.show()
        else:
            self.tray.showMessage("pyload", body)

if __name__ == "__main__":
    app = main()
    app.loop()
