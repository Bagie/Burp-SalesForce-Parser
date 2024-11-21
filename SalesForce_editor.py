from burp import IBurpExtender, IHttpListener, IMessageEditorTabFactory, IMessageEditorTab, ITab
import urllib
import json
from javax.swing import JPanel, JTabbedPane, SwingUtilities, JButton, BoxLayout, JComboBox, JLabel

class BurpExtender(IBurpExtender, IHttpListener, IMessageEditorTabFactory):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks
        self._helpers = callbacks.getHelpers()
        self._original_params = {}  # Initialize _original_params here
        self.highlight_color = "cyan"  # Default highlight color
        callbacks.setExtensionName("SalesForce Parameter Editor")
        callbacks.registerHttpListener(self)
        callbacks.registerMessageEditorTabFactory(self)

        # Create custom UI for reprocessing
        self.createCustomUI()
        print("SalesForce Parameter Editor loaded")

    def processHttpMessage(self, toolFlag, messageIsRequest, messageInfo):
        if messageIsRequest:
            request = messageInfo.getRequest()
            requestInfo = self._helpers.analyzeRequest(request)
            parameters = requestInfo.getParameters()

            # Extract and store parameters if found
            self._original_params = {
                param.getName(): urllib.unquote(param.getValue())
                for param in parameters
                if param.getName() in ["message", "aura.context", "aura.pageURI"]
            }

            # Check if any relevant parameters are present and highlight the request
            if self._original_params:
                messageInfo.setHighlight(self.highlight_color)  # Highlight the request with the selected color

    def createNewInstance(self, controller, editable):
        # Pass a copy of _original_params to avoid sharing state across instances
        return CustomParameterEditor(self._callbacks, controller, editable, dict(self._original_params))

    def createCustomUI(self):
        # Create a panel with a button and color selection for reprocessing
        panel = JPanel()
        panel.setLayout(BoxLayout(panel, BoxLayout.Y_AXIS))

        # Create a dropdown for color selection
        color_label = JLabel("Highlight Color:")
        colors = ["red", "orange", "yellow", "green", "cyan", "blue", "pink", "magenta", "gray"]
        self.color_selector = JComboBox(colors)
        self.color_selector.setSelectedItem(self.highlight_color)
        self.color_selector.addActionListener(self.updateHighlightColor)

        # Create a button for reprocessing
        reprocess_button = JButton("Reprocess History", actionPerformed=self.reprocessHistory)

        # Add components to the panel
        panel.add(color_label)
        panel.add(self.color_selector)
        panel.add(reprocess_button)

        # Add this panel as a new tab in Burp Suite's UI
        self._callbacks.addSuiteTab(CustomUITab(panel, "SF Param Editor"))

    def updateHighlightColor(self, event):
        # Update the highlight color based on user selection
        self.highlight_color = self.color_selector.getSelectedItem()
        print("Highlight color updated to: {}".format(self.highlight_color))

    def reprocessHistory(self, event=None):
        # Reprocess all HTTP history items and highlight relevant requests
        for item in self._callbacks.getProxyHistory():
            request = item.getRequest()
            if request:
                requestInfo = self._helpers.analyzeRequest(request)
                parameters = requestInfo.getParameters()
                # Check for the parameters of interest and highlight accordingly
                if any(param.getName() in ["message", "aura.context", "aura.pageURI"] for param in parameters):
                    item.setHighlight(self.highlight_color)  # Highlight color based on user selection

class CustomUITab(ITab):
    def __init__(self, panel, name):
        self.panel = panel
        self.name = name

    def getTabCaption(self):
        return self.name

    def getUiComponent(self):
        return self.panel

class CustomParameterEditor(IMessageEditorTab):
    def __init__(self, callbacks, controller, editable, original_params):
        self._helpers = callbacks.getHelpers()
        self._editable = editable
        self._controller = controller
        self._original_params = original_params or {}
        self._txtInput_message = callbacks.createTextEditor()
        self._txtInput_aura_context = callbacks.createTextEditor()
        self._txtInput_aura_pageURI = callbacks.createTextEditor()
        self._txtInput_message.setEditable(editable)
        self._txtInput_aura_context.setEditable(editable)
        self._txtInput_aura_pageURI.setEditable(editable)
        self._currentMessage = None
        self._initializeUI()

    def _initializeUI(self):
        self.panel = JTabbedPane()
        self.panel.addTab("message", self._txtInput_message.getComponent())
        self.panel.addTab("aura.context", self._txtInput_aura_context.getComponent())
        self.panel.addTab("aura.pageURI", self._txtInput_aura_pageURI.getComponent())

    def getTabCaption(self):
        return "SalesForce Params Editor"

    def getUiComponent(self):
        return self.panel

    def isEnabled(self, content, isRequest):
        if content is None:
            return False
        requestInfo = self._helpers.analyzeRequest(content)
        parameters = requestInfo.getParameters()
        return any(param.getName() in ["message", "aura.context", "aura.pageURI"] for param in parameters)

    def setMessage(self, content, isRequest):
        SwingUtilities.invokeLater(lambda: self._updateUiContent(content))

    def _updateUiContent(self, content):
        self._currentMessage = content
        if content is None:
            self.clearTextEditors()
            return
        requestInfo = self._helpers.analyzeRequest(content)
        parameters = requestInfo.getParameters()
        for param in parameters:
            decoded_value = urllib.unquote(param.getValue())
            if param.getName() == "message":
                self._setEditorContent(self._txtInput_message, decoded_value)
            elif param.getName() == "aura.context":
                self._setEditorContent(self._txtInput_aura_context, decoded_value)
            elif param.getName() == "aura.pageURI":
                self._setEditorContent(self._txtInput_aura_pageURI, decoded_value)

    def _setEditorContent(self, editor, content):
        try:
            decoded_json = json.loads(content)
            pretty_json = json.dumps(decoded_json, indent=4)
            editor.setText(pretty_json.encode('utf-8'))
        except ValueError:
            editor.setText(content.encode('utf-8'))

    def clearTextEditors(self):
        self._txtInput_message.setText(None)
        self._txtInput_aura_context.setText(None)
        self._txtInput_aura_pageURI.setText(None)

    def getMessage(self):
        if any(editor.isTextModified() for editor in [self._txtInput_message, self._txtInput_aura_context, self._txtInput_aura_pageURI]):
            modified_message = self._getModifiedText(self._txtInput_message)
            modified_aura_context = self._getModifiedText(self._txtInput_aura_context)
            modified_aura_pageURI = self._getModifiedText(self._txtInput_aura_pageURI)
            try:
                requestInfo = self._helpers.analyzeRequest(self._currentMessage)
                parameters = requestInfo.getParameters()
                updated_request = self._currentMessage
                for param in parameters:
                    if param.getName() == "message":
                        updated_request = self._updateParameter(updated_request, param, modified_message)
                    elif param.getName() == "aura.context":
                        updated_request = self._updateParameter(updated_request, param, modified_aura_context)
                    elif param.getName() == "aura.pageURI":
                        updated_request = self._updateParameter(updated_request, param, modified_aura_pageURI)
                return updated_request
            except Exception as e:
                print("Error updating parameters: {}".format(e))
        return self._currentMessage

    def _getModifiedText(self, editor):
        modified_text = editor.getText().tostring()
        try:
            decoded_json = json.loads(modified_text)
            clean_text = json.dumps(decoded_json, separators=(',', ':'))
        except ValueError:
            clean_text = modified_text.replace("\n", "").replace(" ", "")
        return urllib.quote(clean_text)

    def _updateParameter(self, request, param, value):
        new_param = self._helpers.buildParameter(param.getName(), value, param.getType())
        return self._helpers.updateParameter(request, new_param)

    def isModified(self):
        return any(editor.isTextModified() for editor in [self._txtInput_message, self._txtInput_aura_context, self._txtInput_aura_pageURI])
