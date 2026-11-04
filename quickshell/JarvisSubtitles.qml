pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

Scope {
    id: root

    property string subtitleText: ""
    property string statusText: "READY"
    property bool showing: false
    property bool pinned: false
    property bool voiceEnabled: true
    property bool thinking: false
    property bool copied: false
    property double lastTs: -1

    function dismissCard() {
        root.pinned = false
        root.showing = false
        root.thinking = false
        hideTimer.stop()
    }

    Timer {
        id: hideTimer
        interval: 12000
        onTriggered: {
            if (!root.pinned) {
                root.dismissCard()
            }
        }
    }

    Timer {
        id: copiedTimer
        interval: 1200
        onTriggered: root.copied = false
    }

    Timer {
        interval: 100
        running: true
        repeat: true
        onTriggered: subFile.reload()
    }

    IpcHandler {
        target: "jarvis"
        function show(text: string): void {
            root.thinking = false
            root.subtitleText = text
            root.showing = text !== ""
            if (root.showing) {
                hideTimer.interval = Math.max(9000, Math.min(20000, text.length * 110))
                hideTimer.restart()
            }
        }
        function hide(): void {
            if (!root.pinned) root.dismissCard()
        }
    }

    FileView {
        id: subFile
        path: Qt.resolvedUrl(Quickshell.env("HOME") + "/.cache/43pr/jarvis-subtitle.json")
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try {
                const data = JSON.parse(text())
                if (typeof data.voiceEnabled === "boolean") root.voiceEnabled = data.voiceEnabled
                const ts = Number(data.ts || 0)

                // If the file expressly says active: false, always hide (unless pinned)
                if (!data.active) {
                    root.lastTs = ts
                    if (!root.pinned) root.dismissCard()
                    return
                }

                // Never re-open a message with the same timestamp once it has been shown or dismissed!
                if (ts === root.lastTs) return

                root.lastTs = ts
                root.thinking = Boolean(data.thinking)
                root.statusText = String(data.status || (root.thinking ? "ANALYZING..." : (root.voiceEnabled ? "VOICE + HUD" : "TEXT ONLY")))
                root.subtitleText = String(data.text || "")
                root.showing = root.subtitleText !== ""
                if (root.showing) {
                    hideTimer.interval = Number(data.durationMs) || Math.max(9000, Math.min(20000, root.subtitleText.length * 110))
                    hideTimer.restart()
                }
            } catch (e) {
            }
        }
    }

    component HudBtn: Rectangle {
        id: btn
        property string label: ""
        property bool activeState: false
        signal clicked()
        width: btnTxt.implicitWidth + 14
        height: 22
        radius: 6
        color: activeState
            ? Theme.alpha(Theme.accent, 0.28)
            : (btnArea.containsMouse ? Theme.alpha(Theme.text, 0.16) : Theme.alpha(Theme.text, 0.07))
        border.width: 1
        border.color: activeState ? Theme.accent : Theme.alpha(Theme.text, 0.15)

        Text {
            id: btnTxt
            anchors.centerIn: parent
            text: btn.label
            color: btn.activeState ? Theme.accent : Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.bold: true
        }
        MouseArea {
            id: btnArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
    }

    PanelWindow {
        id: win

        // Fixed transparent canvas at top-center so Wayland never stretches/distorts the buffer
        visible: root.showing && root.subtitleText !== ""
        implicitWidth: 740
        implicitHeight: 240
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "jarvis-subtitles"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        anchors { top: true }
        margins { top: 12 }

        mask: Region { item: root.showing ? card : null }

        Item {
            anchors.fill: parent

            Rectangle {
                id: card
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(700, Math.max(440, subLabel.implicitWidth + 44))
                height: headerRow.height + subLabel.implicitHeight + 34
                radius: Theme.radius + 6
                color: Qt.rgba(Theme._bgBase.r, Theme._bgBase.g, Theme._bgBase.b, 0.94)
                border.width: 1
                border.color: root.thinking ? Theme.ok : Theme.accent

                // Top accent glow line
                Rectangle {
                    anchors.top: parent.top
                    anchors.topMargin: 1
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 28
                    height: 2
                    radius: 1
                    color: root.thinking ? Theme.ok : Theme.accent
                    opacity: 0.75

                    SequentialAnimation on opacity {
                        running: root.thinking
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.2; duration: 450 }
                        NumberAnimation { to: 0.95; duration: 450 }
                    }
                }

                // Header bar: Arc reactor dot + JARVIS badge + Status + Quick Action Buttons
                Item {
                    id: headerRow
                    anchors.top: parent.top
                    anchors.topMargin: 10
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    height: 24

                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            color: root.thinking ? Theme.ok : Theme.accent
                            anchors.verticalCenter: parent.verticalCenter

                            SequentialAnimation on opacity {
                                running: root.showing
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.35; duration: 700 }
                                NumberAnimation { to: 1.0; duration: 700 }
                            }
                        }

                        Text {
                            text: "J.A.R.V.I.S."
                            color: Theme.accent
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            font.bold: true
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Rectangle {
                            width: statusLbl.implicitWidth + 10
                            height: 18
                            radius: 4
                            color: Theme.alpha(Theme.text, 0.08)
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                id: statusLbl
                                anchors.centerIn: parent
                                text: root.statusText
                                color: Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: 9
                            }
                        }
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        HudBtn {
                            label: "🔊 Replay"
                            visible: !root.thinking
                            onClicked: {
                                Quickshell.execDetached([
                                    Quickshell.env("HOME") + "/jarvis/venv/bin/python",
                                    Quickshell.env("HOME") + "/jarvis/jarvis.py",
                                    "--replay"
                                ])
                                hideTimer.restart()
                            }
                        }

                        HudBtn {
                            label: root.voiceEnabled ? "🎙️ Voice ON" : "💬 Text Only"
                            activeState: root.voiceEnabled
                            onClicked: {
                                root.voiceEnabled = !root.voiceEnabled
                                root.statusText = root.voiceEnabled ? "VOICE + HUD" : "TEXT ONLY"
                                Quickshell.execDetached([
                                    Quickshell.env("HOME") + "/jarvis/venv/bin/python",
                                    Quickshell.env("HOME") + "/jarvis/jarvis.py",
                                    "--toggle-voice"
                                ])
                                hideTimer.restart()
                            }
                        }

                        HudBtn {
                            label: root.copied ? "✓ Copied" : "📋 Copy"
                            activeState: root.copied
                            visible: !root.thinking
                            onClicked: {
                                Quickshell.execDetached(["wl-copy", root.subtitleText])
                                root.copied = true
                                copiedTimer.restart()
                            }
                        }

                        HudBtn {
                            label: root.pinned ? "📌 Pinned" : "📌 Pin"
                            activeState: root.pinned
                            onClicked: root.pinned = !root.pinned
                        }

                        HudBtn {
                            label: "✕"
                            onClicked: {
                                root.dismissCard()
                                Quickshell.execDetached(["pkill", "-f", "mpv.*jarvis_speech"])
                            }
                        }
                    }
                }

                Rectangle {
                    id: divider
                    anchors.top: headerRow.bottom
                    anchors.topMargin: 6
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    height: 1
                    color: Theme.alpha(Theme.text, 0.1)
                }

                Text {
                    id: subLabel
                    anchors.top: divider.bottom
                    anchors.topMargin: 8
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    text: root.subtitleText
                    color: root.thinking ? Theme.textDim : Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignLeft
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
