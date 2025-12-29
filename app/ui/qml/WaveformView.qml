// app/ui/qml/WaveformView.qml
import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root

    // image://wave/deckA?cache=123
    property url waveTexSource: ""

    // For scrolling DJ view, keep playhead at 0.5 and move zoomStart
    property real playhead: 0.5            // 0..1 within the viewport
    property real playheadWidth: 0.002     // fraction of width (thin vertical line)

    // Scrolling window over the full track (0..1)
    property real zoomStart: 0.0
    property real zoomWidth: 1.0

    // Beat grid lines in VIEWPORT coordinates [0..1]
    // Example: [0.0, 0.125, 0.25, ...] for 8 beats across
    property var beatLines: []

    // Styling
    property color waveColor: "#4d90fe"
    property color bgColor: "#111111"
    property color beatColor: "#ffaa00"
    property real beatOpacity: 0.65
    property real centerLineWidth: 0.002

    Rectangle {
        anchors.fill: parent
        color: root.bgColor
    }

    ShaderEffect {
        id: shader
        anchors.fill: parent

        property variant waveTex: ShaderEffectSource {
            sourceItem: Image {
                source: root.waveTexSource
                smooth: false
                visible: false
            }
            hideSource: true
            live: true
        }

        property color waveColor: root.waveColor
        property color bgColor: root.bgColor

        property real playhead: root.playhead
        property real playheadWidth: root.playheadWidth

        property real zoomStart: root.zoomStart
        property real zoomWidth: root.zoomWidth

        property real centerLineWidth: root.centerLineWidth

        fragmentShader: "qrc:/shaders/waveform.frag.qsb"
    }

    // Beat grid overlay (viewport-relative)
    Item {
        anchors.fill: parent
        Repeater {
            model: root.beatLines.length
            Rectangle {
                width: 1
                height: parent.height
                x: root.beatLines[index] * parent.width
                color: root.beatColor
                opacity: root.beatOpacity
            }
        }
    }
}
