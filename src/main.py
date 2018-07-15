import sys
import os
from PyQt5.QtCore import Qt, QRect, QRegExp, QDir, QThread
from PyQt5.QtGui import QColor, QPainter, QPalette, QSyntaxHighlighter, QFont, QTextCharFormat, QIcon, QTextOption
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QAction, \
    QVBoxLayout, QTabWidget, QFileDialog, QPlainTextEdit, QHBoxLayout, QDialog, qApp, QTreeView, QFileSystemModel,\
    QTextEdit, QSplitter
from pyautogui import hotkey
from qtconsole.qt import QtGui
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
import random
import util
import config
import subprocess
config = config.read()

lineBarColor = QColor(53, 53, 53)


class NumberBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = parent
        self.editor.blockCountChanged.connect(self.update_width)
        self.editor.updateRequest.connect(self.update_on_scroll)
        self.update_width('1')

    def update_on_scroll(self, rect, scroll):
        if self.isVisible():
            if scroll:
                print(scroll)
                self.scroll(0, scroll)
            else:
                self.update()

    def update_width(self, string):
        width = self.fontMetrics().width(str(string)) + 28
        print("update_width:width:" + str(width))
        if self.width() != width:
            self.setFixedWidth(width)

    def paintEvent(self, event):
        if self.isVisible():
            block = self.editor.firstVisibleBlock()
            height = self.fontMetrics().height()
            number = block.blockNumber()
            painter = QPainter(self)
            painter.fillRect(event.rect(), lineBarColor)
            if config['editor']['NumberBarBox']:
                painter.drawRect(0, 0, event.rect().width() - 1, event.rect().height() - 1)

            font = painter.font()

            current_block = self.editor.textCursor().block().blockNumber() + 1

            while block.isValid():
                block_geometry = self.editor.blockBoundingGeometry(block)
                offset = self.editor.contentOffset()
                block_top = block_geometry.translated(offset).top()
                number += 1
                rect = QRect(0, block_top, self.width() - 5, height)

                if number == current_block:
                    font.setBold(True)
                else:
                    font.setBold(False)

                painter.setFont(font)
                painter.drawText(rect, Qt.AlignRight, '%i' % number)

                if block_top > event.rect().bottom():
                    break

                block = block.next()

            painter.end()


class Search(QWidget):
    pass


class Console(QWidget, QThread):
    def __init__(self):
        super().__init__()

        self.editor = QPlainTextEdit(self)
        self.editor.resize(780, 310)

    def execute(self, command):
        """Executes a system command."""

        out, err = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        return (out+err).decode()


class PlainTextEdit(QPlainTextEdit):

    def __init__(self):
        super().__init__()

        editor = config['editor']
        self.font = QFont()

        self.font.setFamily(editor["editorFont"])
        self.font.setPointSize(editor["editorFontSize"])

        self.replace_tabs = 4
        self.setFont(self.font)

        self.setTabStopWidth(editor["TabWidth"])
        self.createStandardContextMenu()

        self.setWordWrapMode(QTextOption.NoWrap)

    def keyPressEvent(self, e):
        key = e.key()
        if key not in [16777217, 16777219, 16777220]:
            super().keyPressEvent(e)
            return

        e.accept()
        cursor = self.textCursor()

        if key == 16777217 and self.replace_tabs:
            amount = 4 - self.textCursor().positionInBlock() % 4
            self.insertPlainText(' ' * amount)
            print(self.toPlainText()[self.textCursor().position():].find('\n') + self.textCursor().positionInBlock())

        elif key == 16777219 and cursor.selectionStart() == cursor.selectionEnd() and self.replace_tabs and \
                cursor.positionInBlock():
            position = cursor.positionInBlock()
            end = cursor.position()
            start = end - (position % 4)

            if start == end and position >= 4:
                start -= 4

            string = self.toPlainText()[start:end]
            if not len(string.strip()):
                for i in range(end - start):
                    cursor.deletePreviousChar()
            else:
                super().keyPressEvent(e)

        elif key == 16777220:
            end = cursor.position()
            start = end - cursor.positionInBlock()
            line = self.toPlainText()[start:end]
            indentation = len(line) - len(line.lstrip())

            chars = '\t'
            if self.replace_tabs:
                chars = '    '
                indentation /= self.replace_tabs

            if line.endswith(':'):
                if self.replace_tabs:
                    indentation += 1

            super().keyPressEvent(e)
            self.insertPlainText(chars * int(indentation))
        else:
            super().keyPressEvent(e)


class Directory(QTreeView):
    def __init__(self, callback):
        super().__init__()

        self.open_callback = callback

        self.layout = QHBoxLayout()
        self.model = QFileSystemModel()
        self.setModel(self.model)
        self.model.setRootPath(QDir.rootPath())

        self.setIndentation(10)
        self.setAnimated(True)

        self.setSortingEnabled(True)
        self.setWindowTitle("Dir View")

        self.hideColumn(1)
        self.resize(200, 600)

        self.hideColumn(2)
        self.hideColumn(3)
        self.layout.addWidget(self)
        self.doubleClicked.connect(self.openFile)
        self.show()

    def openDirectory(self, path):
        self.setRootIndex(self.model.index(path))

    def openFile(self, signal):
        file_path = self.model.filePath(signal)
        self.open_callback(file_path)


class Content(QWidget):
    def __init__(self, text, fileName):
        super().__init__()
        self.editor = PlainTextEdit()
        self.text = text
        self.fileName = fileName
        self.editor.setPlainText(text)
        # Create a layout for the line numbers
        self.hbox = QHBoxLayout(self)
        self.numbers = NumberBar(self.editor)
        self.hbox.addWidget(self.numbers)
        self.hbox.addWidget(self.editor)


class ConsoleWidget(RichJupyterWidget, QThread):

    def __init__(self, *args, **kwargs):
        super(ConsoleWidget, self).__init__(*args, **kwargs)

        self.font_size = 12
        self.kernel_manager = kernel_manager = QtInProcessKernelManager()
        kernel_manager.start_kernel(show_banner=False)
        kernel_manager.kernel.gui = 'qt'
        self.kernel_client = kernel_client = self._kernel_manager.client()
        kernel_client.start_channels()

        def stop():
            kernel_client.stop_channels()
            kernel_manager.shutdown_kernel()
            sys.exit()

        self.exit_requested.connect(stop)

    def push_vars(self, variableDict):
        """
        Given a dictionary containing name / value pairs, push those variables
        to the Jupyter console widget
        """
        self.kernel_manager.kernel.shell.push(variableDict)

    def clear(self):
        """
        Clears the terminal
        """
        self._control.clear()

        # self.kernel_manager

    def print_text(self, text):
        """
        Prints some plain text to the console
        """
        self._append_plain_text(text)

    def execute_command(self, command):
        """
        Execute a command in the frame of the console widget
        """
        self._execute(command, False)


class Tabs(QWidget, QThread):

    def __init__(self, callback):
        super().__init__()
        self.layout = QHBoxLayout(self)  # Change main layout to Vertical
        # Initialize tab screen
        self.tabs = QTabWidget()  # TODO: This is topright
        self.IPyconsole = ConsoleWidget()  # Create IPython widget TODO: This is bottom, this is thread1

        self.IPyconsole.start()  # Starting the FIRST thread
        self.Console = Console()  # This is the terminal widget and the SECOND thread

        self.Console.start()  # Starting the SECOND thread

        self.directory = Directory(callback)  # TODO: This is top left
        self.directory.clearSelection()

        # Add tabs
        self.tab_layout = QHBoxLayout()  # Create new layout for original tab layout
        self.tab_layout.addWidget(self.tabs)  # Add tab widget to tab layout

        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)  # TODO: make this customizable
        self.tabs.setTabShape(1)  # TODO: make this customizable
        self.tabs.tabCloseRequested.connect(self.closeTab)

        # Add Console
        self.console_layout = QHBoxLayout()  # Create console layout
        self.console_layout.addWidget(self.IPyconsole)  # Add console to console layout

        # Build Layout
        self.layout.addLayout(self.tab_layout)  # Adds 'TOP' layout : tab + directory

        # Creating horizontal splitter
        self.splitterH = QSplitter(Qt.Horizontal)

        # Creating vertical splitter
        self.splitterV = QSplitter(Qt.Vertical)
        self.splitterV.addWidget(self.splitterH)
        self.layout.addWidget(self.splitterV)

        self.setLayout(self.layout)  # Sets layout of QWidget

        self.hideDirectory()

    def closeTab(self, index):
        tab = self.tabs.widget(index)
        tab.deleteLater()
        self.tabs.removeTab(index)

    def showDirectory(self):
        self.directory.setVisible(True)
        self.tab_layout.removeWidget(self.tabs)
        self.splitterH.addWidget(self.directory)  # Adding that directory widget in the Tab class BEFORE the tabs
        self.splitterH.addWidget(self.tabs)  # Adding tabs, now the directory tree will be on the left

    def hideDirectory(self):
        self.tab_layout.removeWidget(self.directory)
        self.directory.setVisible(False)

    """
    Because the root layouts are set all you have to do now is just add/remove widgets from the parent layout associated.
    This keeps the UI order set as intended as built above when initialized.
    """

    def showConsole(self):
        #self.splitterV.addWidget(self.console)
        pass

    def hideConsole(self):

        pass


class Main(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.onStart()
        # Initializing the main widget where text is displayed
        self.tab = Tabs(self.openFile)
        self.tabsOpen = []
        self.OS = sys.platform
        print(self.OS)
        self.pyConsoleOpened = None
        self.setWindowIcon(QIcon('resources/Python-logo-notext.svg_.png'))  # Setting the window icon

        self.setWindowTitle('PyPad')  # Setting the window title

        # Without this, the whole layout is broken
        self.setCentralWidget(self.tab)
        self.newFileCount = 0  # Tracking how many new files are opened

        self.files = None  # Tracking the current file that is open
        self.pyFileOpened = False  # Tracking if python file is opened, this is useful to delete highlighting

        self.cFileOpened = False
        self.initUI()  # Main UI

        self.show()

    def onStart(self):
        editor = config['editor']

        if editor["windowStaysOnTop"] is True:
            self.setWindowFlags(Qt.WindowStaysOnTopHint)

        else:
            pass

        self.font = QFont()
        self.font.setFamily(editor["editorFont"])

        self.font.setPointSize(editor["editorFontSize"])
        self.tabSize = editor["TabWidth"]

    def initUI(self):
        self.statusBar()  # Initializing the status bar

        self.font.setFixedPitch(True)

        shortcuts = {
            'Undo': {'shortcut': 'Ctrl+Z'},
            'Redo': {'shortcut': 'Shift+Ctrl+Z'},
            'Cut': {'shortcut': 'Ctrl+X'},
            'Copy': {'shortcut': 'Ctrl+C'},
            'Paste': {'shortcut': 'Ctrl+V'},
            'Select All': {'shortcut': 'Ctrl+A'},
            'New': {'shortcut': 'Ctrl+N', 'tip': 'Create a new file', 'action': self.newFile},
            'Open...': {'shortcut': 'Ctrl+O', 'tip': 'Open a file', 'action': self.openFileFromMenu},
            'Quit': {'shortcut': 'Ctrl+Q', 'tip': 'Exit application', 'action': qApp.quit},
            'Save': {'shortcut': 'Ctrl+S', 'tip': 'Save a file', 'action': self.saveFile},
            'Save As...': {'shortcut': 'Ctrl+Shift+S', 'tip': 'Save a file as', 'action': self.saveFileAs},
            'Python console': {'shortcut': 'Ctrl+Shift+P', 'tip': 'Open a python console', 'action': self.pyConsole},
            'Console': {'shortcut': 'Ctrl+Shift+C', 'tip': 'Open a console', 'action': self.Terminal}
        }

        actions = {}

        for name, values in shortcuts.items():
            actions[name] = QAction(name, self)
            actions[name].setShortcut(values.get('shortcut'))
            actions[name].setStatusTip(values.get('tip', name))
            keys = values.get('shortcut').lower().split('+')
            actions[name].triggered.connect(values.get('action', lambda a='ignore this', keys=keys: hotkey(*keys)))

        menu_bar = self.menuBar()

        menus = {
            'File': ['New', 'Open...', 'Save', 'Save As...', 'Separator', 'Quit'],
            'Edit': ['Undo', 'Redo', 'Separator', 'Cut', 'Copy', 'Paste', 'Separator', 'Select All'],
            'Tools': ['Python console', 'Console']
        }

        for name, items in menus.items():
            menu = menu_bar.addMenu(name)
            for item in items:
                if item == 'Separator':
                    menu.addSeparator()
                    continue
                menu.addAction(actions[item])

        self.resize(800, 700)

    def openFileFromMenu(self):
        self.tab.hideDirectory()
        options = QFileDialog.Options()

        filenames, _ = QFileDialog.getOpenFileNames(
            self, 'Open a file', '',
            'All Files (*);;Python Files (*.py);;Text Files (*.txt)',
            options=options
        )
        tab_idx = len(self.tabsOpen)

        if filenames:  # If file is selected, we can open it
            filename = filenames[0]
            self.openFile(filename)

    def openFile(self, filename):
        with open(filename, 'r+') as file_o:
            text = file_o.read()
            tab = Content(text, filename)  # Creating a tab object *IMPORTANT*

            dirPath = os.path.dirname(filename)
            self.files = filename

            self.tabsOpen.append(self.files)

            index = self.tab.tabs.addTab(tab,
                                         tab.fileName)  # This is the index which we will use to set the current index

            self.tab.directory.openDirectory(dirPath)

            self.tab.showDirectory()

            self.tab.setLayout(self.tab.layout)  # Finally we set the layout

            self.tab.tabs.setCurrentIndex(index)  # Setting the index so we could find the current widget
            self.currentTab = self.tab.tabs.currentWidget()

            self.currentTab.editor.setFont(self.font)  # Setting the font
            self.currentTab.editor.setTabStopWidth(self.tabSize)  # Setting tab size
            self.currentTab.editor.setFocus()  # Setting focus to the tab after we open it

            if filename.endswith(".py"):
                self.pyFileOpened = True
                self.pyhighlighter = PyHighlighter(
                    self.currentTab.editor.document())  # Creating the highlighter for python

            elif filename.endswith(".c"):
                self.cFileOpened = True
                self.chighlighter = CHighlighter(self.currentTab.editor.document())

            else:
                if self.pyFileOpened:
                    del self.pyhighlighter
                if self.cFileOpened:
                    del self.chighlighter

    def newFile(self):
        text = ""
        fileName = "New" + str(random.randint(1, 2000000)) + ".py"
        self.pyFileOpened = True
        # Creates a new blank file
        file = Content(text, fileName)

        self.tab.splitterH.addWidget(self.tab.tabs)  # Adding tabs, now the directory tree will be on the left

        self.tab.setLayout(self.tab.layout)  # Finally we set the layout
        index = self.tab.tabs.addTab(file, file.fileName)  # addTab method returns an index for the tab that was added
        self.tab.tabs.setCurrentIndex(index)  # Setting "focus" to the new tab that we created

        widget = self.tab.tabs.currentWidget()
        self.pyhighlighter = PyHighlighter(widget.editor.document())  # Creating the highlighter for python file
        widget.editor.setFocus()
        widget.editor.setFont(self.font)
        widget.editor.setTabStopWidth(self.tabSize)

    def saveFile(self):
        try:
            active_tab = self.tab.tabs.currentWidget()

            if self.tab.tabs.count():  # If a file is already opened
                with open(active_tab.fileName, 'w+') as saveFile:
                    self.saved = True
                    saveFile.write(active_tab.editor.toPlainText())


                    saveFile.close()
            else:
                options = QFileDialog.Options()
                name = QFileDialog.getSaveFileName(self, 'Save File', '',
                                                   'All Files (*);;Python Files (*.py);;Text Files (*.txt)',
                                                   options=options)
                fileName = name[0]
                with open(fileName, "w+") as saveFile:
                    self.saved = True

                    self.tabsOpen.append(fileName)
                    saveFile.write(active_tab.editor.toPlainText())

                    saveFile.close()
        except:
            print("File dialog closed or no file opened")

    def saveFileAs(self):
        try:
            active_tab = self.tab.tabs.currentWidget()
            if active_tab is not None:
                active_index = self.tab.tabs.currentIndex()

                options = QFileDialog.Options()
                name = QFileDialog.getSaveFileName(self, 'Save File', '',
                                                   'All Files (*);;Python Files (*.py);;Text Files (*.txt)',
                                                   options=options)
                fileName = name[0]
                with open(fileName, "w+") as saveFile:
                    self.saved = True
                    self.tabsOpen.append(fileName)

                    saveFile.write(active_tab.editor.toPlainText())
                    text = active_tab.editor.toPlainText()
                    newTab = Content(str(text), fileName)

                    self.tab.tabs.removeTab(active_index)  # When user changes the tab name we make sure we delete the old one
                    index = self.tab.tabs.addTab(newTab, newTab.fileName)  # And add the new one!

                    self.tab.tabs.setCurrentIndex(index)
                    newActiveTab = self.tab.tabs.currentWidget()

                    newActiveTab.editor.setFont(self.font)
                    newActiveTab.editor.setFocus()

                    if fileName.endswith(".py"):  # If we are dealing with a python file we use highlighting on it
                        self.pyhighlighter = PyHighlighter(newActiveTab.editor.document())

                        newActiveTab.editor.setTabStopWidth(self.tabSize)
                    elif fileName.endswith(".c"):

                        self.chighlighter = CHighlighter(newActiveTab.editor.document())
                        newActiveTab.editor.setTabStopWidth(self.tabSize)

                    saveFile.close()

            else:
                print("No file opened")

        except FileNotFoundError:
            print("File dialog closed")

    def pyConsole(self):
        if self.OS != "win32":
            self.pyConsoleOpened = True
            self.ind = self.tab.splitterV.indexOf(self.tab.IPyconsole)

            self.o = self.tab.splitterV.indexOf(self.tab.Console)

            if self.tab.splitterV.indexOf(self.tab.Console) == -1:  # If the Console widget DOESNT EXIST YET!

                self.tab.splitterV.addWidget(self.tab.IPyconsole)
                self.ind = self.tab.splitterV.indexOf(self.tab.IPyconsole)

            if self.tab.splitterV.indexOf(self.tab.IPyconsole) == -1:  # If the IPyconsole widget doesnt exist yet
                self.tab.splitterV.replaceWidget(self.o, self.tab.IPyconsole)
                print(self.o)
                self.o = self.tab.splitterV.indexOf(self.tab.Console)

                self.ind = self.tab.splitterV.indexOf(self.tab.IPyconsole)
        else:
            pass
    def Terminal(self):

        active_tab = self.tab.tabs.currentWidget()
        if self.pyConsoleOpened:
            self.o = self.tab.splitterV.indexOf(self.tab.Console)

            self.ind = self.tab.splitterV.indexOf(self.tab.IPyconsole)
            if self.ind == -1:
                self.tab.Console.editor.setPlainText(self.tab.Console.execute("python " + active_tab.fileName))
            else:
                self.tab.splitterV.replaceWidget(self.ind, self.tab.Console)


            try:
                self.tab.Console.execute("python " + active_tab.fileName)
            except AttributeError:

                print("Can't run a file that doesn't exist...")
        else:
            self.tab.splitterV.addWidget(self.tab.Console)

            try:
                active_tab = self.tab.tabs.currentWidget()
                print(active_tab.fileName)
                self.tab.Console.editor.setPlainText(self.tab.Console.execute("python " + active_tab.fileName))
                print(self.tab.Console.editor.toPlainText())

            except AttributeError:
                print("Can't run a file that doesn't exist...")


class PyHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, *args):
        super(PyHighlighter, self).__init__(parent, *args)

        python = config['files']['python']

        self.highlightingRules = []
        self.formats = {}

        for name, values in python['highlighting'].items():
            self.formats[name] = QTextCharFormat()

            if values.get('bold'):
                self.formats[name].setFontWeight(QFont.Bold)
            self.formats[name].setFontItalic(values.get('italic', False))

            self.formats[name].setForeground(QColor(python['highlighting'][name]['color']))
            for regex in util.make_list(values.get('regex', [])):
                self.highlightingRules.append((QRegExp(regex), self.formats[name]))

        self.highlightingRules = [(QRegExp('\\b' + pattern + '\\b'), self.formats['keyword'])
                                  for pattern in python['keywords']] + self.highlightingRules

    def highlightBlock(self, text):
        for pattern, format in self.highlightingRules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)
        self.setCurrentBlockState(0)

        comment = QRegExp("'''")

        if self.previousBlockState() == 1:
            start_index = 0
            index_step = 0
        else:
            start_index = comment.indexIn(text)
            while start_index >= 0 and self.format(start_index+2) in self.formats.values():
                start_index = comment.indexIn(text, start_index + 3)
            index_step = comment.matchedLength()
        while start_index >= 0:
            end = comment.indexIn(text, start_index + index_step)
            if end != -1:
                self.setCurrentBlockState(0)
                length = end - start_index + comment.matchedLength()
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start_index
            self.setFormat(start_index, length, self.formats['multiLineComment'])
            start_index = comment.indexIn(text, start_index + length)


class CHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, *args):
        super(CHighlighter, self).__init__(parent, *args)

        python = config['files']['c']

        self.highlightingRules = []
        self.formats = {}

        for name, values in python['highlighting'].items():
            self.formats[name] = QTextCharFormat()

            if values.get('bold'):
                self.formats[name].setFontWeight(QFont.Bold)
            self.formats[name].setFontItalic(values.get('italic', False))

            self.formats[name].setForeground(QColor(python['highlighting'][name]['color']))
            for regex in util.make_list(values.get('regex', [])):
                self.highlightingRules.append((QRegExp(regex), self.formats[name]))

        self.highlightingRules = [(QRegExp('\\b' + pattern + '\\b'), self.formats['keyword'])
                                  for pattern in python['keywords']] + self.highlightingRules

    def highlightBlock(self, text):
        for pattern, format in self.highlightingRules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)
            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)
        self.setCurrentBlockState(0)

        comment = QRegExp("'''")

        if self.previousBlockState() == 1:
            start_index = 0
            index_step = 0
        else:
            start_index = comment.indexIn(text)
            while start_index >= 0 and self.format(start_index+2) in self.formats.values():
                start_index = comment.indexIn(text, start_index + 3)
            index_step = comment.matchedLength()
        while start_index >= 0:
            end = comment.indexIn(text, start_index + index_step)
            if end != -1:
                self.setCurrentBlockState(0)
                length = end - start_index + comment.matchedLength()
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start_index
            self.setFormat(start_index, length, self.formats['multiLineComment'])
            start_index = comment.indexIn(text, start_index + length)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    palette = QPalette()

    editor = config['editor']

    palette.setColor(QPalette.Window, QColor(editor["windowColor"]))
    palette.setColor(QPalette.WindowText, QColor(editor["windowText"]))
    palette.setColor(QPalette.Base, QColor(editor["editorColor"]))
    palette.setColor(QPalette.AlternateBase, QColor(editor["alternateBase"]))
    palette.setColor(QPalette.ToolTipBase, QColor(editor["ToolTipBase"]))
    palette.setColor(QPalette.ToolTipText, QColor(editor["ToolTipText"]))
    palette.setColor(QPalette.Text, QColor(editor["editorText"]))
    palette.setColor(QPalette.Button, QColor(editor["buttonColor"]))
    palette.setColor(QPalette.ButtonText, QColor(editor["buttonTextColor"]))
    palette.setColor(QPalette.Highlight, QColor(editor["HighlightColor"]).lighter())
    palette.setColor(QPalette.HighlightedText, QColor(editor["HighlightedTextColor"]))
    app.setPalette(palette)

    ex = Main()
    sys.exit(app.exec_())
