"""Bundled, offline help and the first-run introduction for Lunar HDR Studio."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)


@dataclass(frozen=True)
class HelpTopic:
    key: str
    title: str
    summary: str
    body: str


HELP_TOPICS = (
    HelpTopic("quick-start", "Getting started", "Your first Moon composite in seven steps.", """
<p>Combine two or more photographs of the <b>same Moon, taken close together</b>.
A dark exposure can preserve bright surface detail; a normal exposure gives a useful
reference; a bright exposure can reveal faint surroundings and glow.</p>
<ol>
<li><b>Add your exposures.</b> Click <b>Add exposures</b> and select two or more files.
FITS, PNG, JPEG and TIFF are supported. Adding your own files replaces the synthetic demo.</li>
<li><b>Choose a reference.</b> In the left panel, pick a sharp frame with a clear lunar
edge and visible craters. Its dimensions define the output canvas before cropping.</li>
<li><b>Check the exposure values.</b> Each card has an EV field. FITS exposure times
can fill these automatically. Otherwise, enter the actual relative EV values, or
choose <b>Exposure fusion</b> if they are unknown.</li>
<li><b>Align and merge.</b> Run the main button at the bottom of the left panel.
Wait for processing to finish, then inspect the lunar edge and alignment report.</li>
<li><b>Develop the image.</b> Try Natural, Mineral Moon, Silver or Earthshine.
Use the right-hand sliders and <b>Before / after</b> to refine the result.</li>
<li><b>Finish.</b> Scroll down the right panel to choose the star background,
crop the image and add an optional text signature.</li>
<li><b>Export.</b> Use PNG for sharing, 16-bit TIFF for further editing, or JPEG
for a smaller file. Choose a writable destination such as Pictures or Desktop.</li>
</ol>
<h2>Try the controls first</h2>
<p>The built-in demo is clearly labeled <b>SYNTHETIC DEMO</b>. It is practice data,
not a photograph or a mineral map. <b>Open demo</b> loads it again and replaces the
current exposures, so export any result you want to keep first.</p>
<p>Your source files are never modified. Editing projects are <b>not saved between
sessions</b>: export your finished image before closing the app.</p>
<p>Use the topics on the left, the Next button, or search for a control. You can
keep this guide open beside the workspace and reopen it any time with <b>?</b> or <b>F1</b>.</p>
"""),
    HelpTopic("import", "Files, FITS & exposure", "Load frames and set meaningful relative EV values.", """
<h2>Adding and organizing frames</h2>
<p>Use <b>Add exposures</b> or <b>Add files</b> to select multiple files. New files
are appended to real exposures already loaded. Change a single frame with its
card button, or drop one local file onto that card. The <b>×</b> button removes it
from this session without deleting the file. At least two frames are needed to merge.</p>
<p>Choose the reference in the left panel. A sharp, moderately exposed image with
shared surface detail is usually easiest to align. Changing the reference also
recalculates relative EV and requires a new merge.</p>
<h2>What EV means here</h2>
<p>The EV box on each source card describes the <b>capture exposure relative to
the reference</b>. Keep the reference at 0 EV. A darker exposure is negative; a
brighter exposure is positive. One stop means twice or half the light.</p>
<table cellspacing="0" cellpadding="8" border="1">
<tr><th>Exposure time</th><th>Relative EV</th><th>Role</th></tr>
<tr><td>1/1000 second</td><td>−2</td><td>Underexposed</td></tr>
<tr><td>1/250 second</td><td>0</td><td>Reference</td></tr>
<tr><td>1/60 second</td><td>About +2</td><td>Overexposed</td></tr>
</table>
<p>This example assumes the same gain/ISO, aperture and filter. For exact values,
EV = log2(exposure time / reference time). <b>Initial zeros are placeholders, not
measured exposure differences.</b> JPEG EXIF exposure times are not read automatically.</p>
<p>If every frame has a valid FITS <code>EXPTIME</code> or <code>EXPOSURE</code>,
the app suggests EV values. Editing an EV switches to manual values. Check stacked
FITS carefully: total integration time may not represent the brightness of a
normalized stack. A very large time range triggers a warning. For uncertain data,
try <a href="help:merge">Exposure fusion</a>.</p>
<h2>Supported FITS data</h2>
<p>The first image HDU is used, including image extensions, gzip files and compressed
<code>.fits.fz</code> images. 2D monochrome and three-channel RGB are supported.
Invalid samples are masked; header scaling is respected. The contrast stretch shown
in the preview does not change the original linear data used for HDR.</p>
<p>Debayer raw 2D Bayer data first. Select a plane from a spectral/time cube before
importing. Already-developed RGB FITS with a leftover Bayer header is accepted with
a warning. For camera RAW or SER, export a color TIFF first; use sRGB for ordinary images.</p>
<p>There is no fixed frame-count limit, but full-resolution stacks need RAM.
Hover over the cards or status messages for file warnings.</p>
"""),
    HelpTopic("alignment", "Align the lunar disks", "Check registration and correct a double edge.", """
<h2>Automatic alignment</h2>
<p>The main merge button detects lunar disks and shared surface features, then aligns
translation, rotation and scale to the selected reference. Output uses the reference
frame's canvas. Areas outside it are not preserved by switching to a brighter exposure.</p>
<p>Inspect the disk edge, craters and the <b>Disk alignment</b> report. A confidence
score describes the registration estimate; it is not a guarantee. If a report says
to check manually, use <b>Fine-tune…</b> before trusting the merged detail. Hover over
the report to read additional diagnostics for every frame.</p>
<h2>Manual refinement</h2>
<ol>
<li>Click <b>Fine-tune…</b> after an automatic merge.</li>
<li>Select a non-reference exposure. The reference stays fixed.</li>
<li>Move <b>X</b> and <b>Y</b> to line up the disk; adjust <b>Rotation</b> and
<b>Scale</b> if one limb matches but the other does not. Scale 1 means no extra scaling.</li>
<li>Watch the overlay: <b>red = reference, cyan = selected exposure</b>. Neutral
edges indicate overlap. The brightness is normalized, so differences in exposure
or clipping can still create colors even when the frames line up.</li>
<li>Apply the corrections to recalculate the composite. Reset selected removes
that frame's extra correction; Cancel keeps the previous alignment.</li>
</ol>
<p>These are corrections <b>on top of automatic alignment</b>, not absolute positions.
If you run the main automatic merge again, manual corrections are reset.</p>
<h2>Preview controls</h2>
<p>Use the wheel or +/− buttons to zoom, drag to pan, and double-click or press
<b>Fit</b> to recenter. With <b>Before / after</b> enabled, drag the divider:
the reference is on the left and the result on the right. This comparison uses the
selected reference, not a previous edit. Zoom is relative to fitting the preview;
the preview is reduced for responsiveness, while export uses full resolution.</p>
<p>Severe clipping, clouds, extreme crops or too few shared craters can prevent
reliable matching. Try a better reference or remove a problematic frame. Alignment
does not fix local atmospheric distortion or align background stars independently.</p>
"""),
    HelpTopic("merge", "HDR or exposure fusion", "Choose a merge mode that fits your input data.", """
<h2>HDR · exposure times / EV</h2>
<p>Use HDR when you know the exposure relationship between the frames. It combines
linear light values while accounting for source EV and produces a tone-mapped preview
plus a linear radiance result that can be exported as <code>.hdr</code>.</p>
<p>For ordinary PNG/JPEG/TIFF images, the app assumes an sRGB response before merging.
This is relative HDR, not a calibrated measurement of lunar brightness. The source
EV values affect the merge; the <b>Exposure slider in Develop</b> changes the look
of the result afterwards.</p>
<h2>FITS radiometric HDR</h2>
<p>FITS HDR uses original linear samples and exposure metadata. Compatible count
units such as ADU, DN, counts, electrons and photons are supported, including
per-second forms. Rates are not divided by exposure time a second time.</p>
<p>Keep calibration, units, gain, aperture and filters consistent. Mixed ordinary
sRGB images and FITS cannot share one radiometric merge; use separate batches or fusion. Units
such as Jy/sr require conversion first. If you need a visual combination of incompatible
or normalized data, use fusion instead.</p>
<h2>Exposure fusion · uncalibrated</h2>
<p>Fusion blends usable regions of the displayed exposures without needing calibrated
EV values. It is a useful starting point when exposure times are missing or unreliable.
It produces a displayable image, <b>not linear HDR radiance</b>, so export is PNG,
JPEG or TIFF. Choosing fusion does not make the captured data scientifically calibrated.</p>
<h2>When to merge again</h2>
<p>Adding, replacing or removing a frame, changing the reference, source EV values
or merge method requires recalculation. Export stays disabled while the merge is
out of date or processing is running. Sliders, cropping, stars and signatures update
the preview without requiring another alignment.</p>
<p>No method can recover detail clipped in every input. A bright halo is controlled
by what the exposure stack captured and by your adjustments; a black sky is not required.</p>
"""),
    HelpTopic("develop", "Color & Mineral Moon", "Understand presets and every adjustment slider.", """
<h2>Start with a preset</h2>
<p><b>Natural</b> gives a restrained starting point. <b>Mineral Moon</b> neutralizes
the overall cast and amplifies existing surface colors. <b>Silver</b> is monochrome.
<b>Earthshine</b> raises faint tones. Presets replace the development slider values;
you can adjust them afterwards.</p>
<h2>Adjustment controls</h2>
<ul>
<li><b>Exposure:</b> brighten or darken the developed result in stops. It does not
replace the source-card EV values used during HDR merging.</li>
<li><b>Contrast:</b> change separation between darker and brighter tones.</li>
<li><b>Highlights:</b> reduce bright areas or make them more prominent. Lowering it
cannot reconstruct detail that was clipped in all captures.</li>
<li><b>Shadows:</b> reveal or darken faint tones. Raising them can reveal noise too.</li>
<li><b>Color neutralization:</b> reduce an overall color cast using the bright lunar
disk as an approximately neutral-gray reference. 0% disables it; reduce it if the
correction does not suit your data.</li>
<li><b>Temperature:</b> shift the image toward cooler or warmer tones.</li>
<li><b>Saturation:</b> control overall color strength. 100% is the neutral setting;
0% removes color.</li>
<li><b>Mineral colors:</b> selectively amplify recorded lunar surface color differences
while protecting brightness and the surrounding glow.</li>
<li><b>Clarity:</b> emphasize nearby tonal differences for a stronger sense
of texture. Too much can exaggerate halos.</li>
<li><b>Sharpness:</b> emphasize edges; use moderately to avoid ringing and noisy craters.</li>
<li><b>Noise reduction:</b> smooth noise. Higher values can also soften detail.</li>
</ul>
<h2>A practical Mineral Moon workflow</h2>
<p>Use color frames with visible surface detail, verify alignment, then try Mineral
Moon. Adjust color neutralization before increasing mineral colors. Keep saturation
moderate, and balance clarity, sharpness and noise reduction while comparing
against the reference. If the disk becomes blotchy, lower mineral colors and saturation.</p>
<p>The colors depend on your photographs: the app does not impose a blue/copper
palette, invent missing color or identify minerals. Grayscale images contain no
recorded color to enhance. When all inputs are identified as monochrome FITS, color
controls are disabled. Poor white balance, color noise and clipped channels limit the result.</p>
<p><b>Reset</b> restores development defaults and clears stars, crop and signature
enablement. Your typed signature text is retained, and the exposure stack stays loaded.</p>
"""),
    HelpTopic("finishing", "Stars, crop & signature", "Finish the composition without changing the source files.", """
<p>Scroll down inside the right-hand Develop panel to find <b>Finishing</b>.</p>
<h2>Background stars</h2>
<ul>
<li><b>Original background:</b> keep the merged background, including captured glow.</li>
<li><b>Suppress stars:</b> estimate and suppress small bright points outside the lunar
disk. Inspect the result; small bright features can be misidentified.</li>
<li><b>Add stars · effect:</b> add a synthetic visual star overlay. These stars are
not recorded astronomical objects. Disclose the effect if you share the image.</li>
</ul>
<p>These options are independent of the Mineral Moon preset. There is no requirement
to make the sky black. Select Original background to preserve the appearance created
by your exposure stack and development settings.</p>
<h2>Crop</h2>
<p>Click <b>Crop</b>, then drag a rectangle on the image. Apply it to the preview
and raster exports. Cancel leaves the previous crop unchanged; <b>Reset crop</b>
restores the full canvas. The source files are never cropped. The crop editor shows
the image without a signature so it cannot obstruct your selection.</p>
<h2>Text signature</h2>
<p>Enable <b>Add signature</b> and type your text (up to 100 characters). The app
places the signature on the finished crop. Edit the text to change it, or uncheck
the option to remove it. This control adds text, not an uploaded signature image.</p>
<h2>Which exports include finishing?</h2>
<p>PNG, JPEG and 16-bit TIFF include the crop, signature, background choice and
development adjustments. <b>Linear Radiance HDR deliberately exports the full base
merge without these edits.</b> See <a href="help:export">Export & file formats</a>.</p>
"""),
    HelpTopic("export", "Export & file formats", "Save the finished preview or the unedited linear HDR data.", """
<h2>Save a finished image</h2>
<ol>
<li>Finish the merge and inspect the preview. If Export is disabled, wait for the
current task or run the merge again after changing its inputs.</li>
<li>Click <b>Export image</b> and choose a file format in the save dialog.</li>
<li>Choose a writable folder and a filename. The dialog starts in Pictures (or your
home folder) and remembers successful destinations for this session.</li>
<li>Save and wait for the exported-path message in the status bar.</li>
</ol>
<table cellspacing="0" cellpadding="8" border="1">
<tr><th>Format</th><th>Use it for</th><th>What is saved</th></tr>
<tr><td>PNG</td><td>Sharing a lossless finished image</td><td>8-bit developed image with finishing</td></tr>
<tr><td>JPEG</td><td>A smaller, widely supported file</td><td>8-bit developed image; lossy compression</td></tr>
<tr><td>16-bit TIFF</td><td>Further editing with more tonal precision</td><td>Developed image with finishing</td></tr>
<tr><td>Radiance HDR (.hdr)</td><td>Further processing in HDR software</td><td>Full base linear merge, no tone mapping or creative edits</td></tr>
</table>
<p>Raster exports are calculated at full source-composite resolution, then cropped
if requested. The on-screen preview is reduced for speed. A 16-bit TIFF does not
restore information missing from 8-bit source files.</p>
<h2>Why an HDR file looks different</h2>
<p>The <code>.hdr</code> file omits development sliders, star effects, cropping,
signatures and the preview tone mapping. An HDR-aware editor must map its linear
values for display. If you want the finished appearance you see in the app, choose
PNG or TIFF. Exposure fusion has no linear HDR export.</p>
<h2>Write errors</h2>
<p>If you see “Read-only file system” or “Permission denied”, select Pictures,
Desktop or another writable folder. Do not save at the filesystem root
(for example <code>/Lunar-HDR.png</code>). Also check free disk space and removable
drive availability. The composite remains available after a failed export, so you
can retry without processing the stack again.</p>
<p>Export saves an image, not an editable project. This version cannot restore all
frames and settings when reopened.</p>
"""),
    HelpTopic("troubleshooting", "Troubleshooting", "Resolve common import, alignment, color and export problems.", """
<h2>Buttons are disabled</h2>
<p>Align/merge needs at least two loaded frames. Fine-tune needs a completed automatic
alignment. Export needs a completed, current composite. A background task temporarily
disables conflicting controls; wait for the status bar to finish. Help remains available.</p>
<h2>Double lunar edge or mismatched craters</h2>
<p>Pick a sharper reference and inspect <a href="help:alignment">manual alignment</a>.
Remove a frame with clouds, extreme clipping or too little shared detail. A sharp
disk against a halo can confuse registration; use the red/cyan overlay to check it.</p>
<h2>The result is too bright, flat or unusually dark</h2>
<p>Check capture EV signs and differences, then merge again. Initial zero EV is not
an automatic brightness estimate. Check whether FITS files are normalized stacks or
already contain count rates. Try fusion if you do not know the exposure relationship.
Then use Exposure and Highlights to set the display brightness.</p>
<h2>Mineral colors look noisy, or color controls are disabled</h2>
<p>Grayscale images have no recorded color to enhance. When all inputs are identified
as monochrome FITS, color controls are disabled. With color data, check neutralization
and reduce mineral colors, saturation
or sharpening. More amplification cannot replace clean, unclipped source color.</p>
<h2>FITS cannot be read or merged</h2>
<p>Use a 2D image or a supported RGB array. Debayer raw sensor mosaics and choose a
plane from cubes first. For HDR, match units and calibration across frames; unsupported
units need conversion. Read the error details and warnings instead of treating an
arbitrary cube as an RGB image. See <a href="help:import">Files, FITS & exposure</a>.</p>
<h2>The app is slow or runs out of memory</h2>
<p>Large images and many frames need substantial RAM. Start with fewer frames or
smaller copies to check alignment, then use the full data. Export recalculates at
full resolution and may take longer than preview adjustments. Wait for processing
before closing the app; source files stay unchanged.</p>
<h2>My exported image is different, or saving fails</h2>
<p>Use PNG/JPEG/TIFF for the edited result. Linear HDR omits creative and finishing
edits. If the destination is read-only, choose a writable folder and retry.
See <a href="help:export">Export & file formats</a> for the exact differences.</p>
<h2>What should I include in a bug report?</h2>
<p>Include your operating system, app version, input formats, frame dimensions,
merge mode and the exact error text. Explain the steps that caused it and whether
the synthetic demo reproduces it. Share private source photographs only if you want to.</p>
"""),
)


class HelpDialog(QDialog):
    """Searchable guide; opening it never touches the editing session."""

    def __init__(self, parent=None, initial_topic="quick-start"):
        super().__init__(parent)
        self.setWindowTitle("Lunar HDR Studio · Help")
        self.setModal(False)
        self.resize(980, 720)
        self.setMinimumSize(740, 500)
        self.setStyleSheet("""
            QDialog { background: #111517; color: #dbe3e5; }
            QLabel#helpTitle { color: #edf4f2; font-size: 24px; font-weight: 600; }
            QLabel#helpSubtitle, QLabel#helpFooter { color: #98adb2; }
            QLineEdit { background: #182226; color: #e4eeeb; border: 1px solid #40534f;
                        border-radius: 6px; padding: 9px; }
            QListWidget { background: #171f22; color: #becdce; border: 1px solid #303e42;
                          border-radius: 8px; padding: 6px; outline: none; }
            QListWidget::item { padding: 12px 8px; border-radius: 4px; }
            QListWidget::item:selected { background: #29443c; color: #ccede4; }
            QListWidget::item:hover { background: #243136; }
            QTextBrowser { background: #171f22; color: #dbe3e5; border: 1px solid #303e42;
                           border-radius: 8px; padding: 14px; }
            QPushButton { padding: 9px 14px; }
        """)
        self._topics = {topic.key: topic for topic in HELP_TOPICS}
        self._search_text = {}
        for topic in HELP_TOPICS:
            document = QTextDocument()
            document.setHtml(topic.body)
            self._search_text[topic.key] = (topic.title + " " + topic.summary + " " +
                                            document.toPlainText()).casefold()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        title = QLabel("Make your first Moon composite")
        title.setObjectName("helpTitle")
        layout.addWidget(title)
        subtitle = QLabel("A practical guide to the whole workflow, available offline.")
        subtitle.setObjectName("helpSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(14)
        sidebar = QWidget()
        sidebar.setFixedWidth(224)
        navigation = QVBoxLayout(sidebar)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("helpSearch")
        self.search_input.setAccessibleName("Search help")
        self.search_input.setPlaceholderText("Search help…")
        self.search_input.setClearButtonEnabled(True)
        navigation.addWidget(self.search_input)
        self.topic_list = QListWidget()
        self.topic_list.setObjectName("helpTopics")
        self.topic_list.setAccessibleName("Help topics")
        navigation.addWidget(self.topic_list, 1)
        body.addWidget(sidebar)
        self.content = QTextBrowser()
        self.content.setObjectName("helpContent")
        self.content.setAccessibleName("Help article")
        self.content.setOpenLinks(False)
        self.content.setOpenExternalLinks(False)
        self.content.document().setDefaultStyleSheet("""
            body { font-family: sans-serif; font-size: 13px; color: #dbe3e5; }
            h1 { font-size: 24px; color: #b9e4d6; margin-bottom: 8px; }
            h2 { font-size: 16px; color: #b9e4d6; margin-top: 22px; }
            p, li { line-height: 145%; }
            li { margin-bottom: 9px; }
            a { color: #a8dbce; }
            th { background-color: #293d37; color: #e4f0eb; }
            td { border-color: #43554f; }
            code { color: #c7e5df; }
        """)
        body.addWidget(self.content, 1)
        layout.addLayout(body, 1)
        footer = QHBoxLayout()
        self.previous_button = QPushButton("← Previous")
        self.previous_button.setObjectName("helpPrevious")
        self.next_button = QPushButton("Next →")
        self.next_button.setObjectName("helpNext")
        footer.addWidget(self.previous_button)
        footer.addWidget(self.next_button)
        footer.addStretch()
        self.close_button = QPushButton("Start editing")
        self.close_button.setObjectName("primary")
        self.close_button.setDefault(True)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        note = QLabel("Offline guide · Your original files stay unchanged · Reopen with ? or F1")
        note.setObjectName("helpFooter")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.search_input.textChanged.connect(self._filter_topics)
        self.topic_list.currentItemChanged.connect(self._show_current)
        self.previous_button.clicked.connect(lambda: self._move(-1))
        self.next_button.clicked.connect(lambda: self._move(1))
        self.close_button.clicked.connect(self.accept)
        self.content.anchorClicked.connect(self._follow_link)
        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(self._focus_search)
        self._filter_topics("")
        self.select_topic(initial_topic)

    @property
    def current_topic(self):
        item = self.topic_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def select_topic(self, key):
        if key not in self._topics:
            key = "quick-start"
        self.search_input.clear()
        for row in range(self.topic_list.count()):
            if self.topic_list.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.topic_list.setCurrentRow(row)
                return

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _filter_topics(self, query):
        previous = self.current_topic
        words = query.casefold().split()
        self.topic_list.blockSignals(True)
        self.topic_list.clear()
        selected = 0
        for topic in HELP_TOPICS:
            if all(word in self._search_text[topic.key] for word in words):
                item = QListWidgetItem(topic.title)
                item.setData(Qt.ItemDataRole.UserRole, topic.key)
                item.setToolTip(topic.summary)
                self.topic_list.addItem(item)
                if topic.key == previous:
                    selected = self.topic_list.count() - 1
        if self.topic_list.count():
            self.topic_list.setCurrentRow(selected)
        self.topic_list.blockSignals(False)
        self._show_current()

    def _show_current(self, *_args):
        key = self.current_topic
        if key is None:
            self.content.setHtml("<h1>No matching topics</h1><p>Try a shorter term such as "
                                 "FITS, EV, crop, stars or export, or clear the search.</p>")
        else:
            topic = self._topics[key]
            self.content.setHtml(f"<h1>{topic.title}</h1><p><i>{topic.summary}</i></p>{topic.body}")
        self.content.verticalScrollBar().setValue(0)
        row = self.topic_list.currentRow()
        self.previous_button.setEnabled(row > 0)
        self.next_button.setEnabled(0 <= row < self.topic_list.count() - 1)

    def _move(self, delta):
        row = self.topic_list.currentRow() + delta
        if 0 <= row < self.topic_list.count():
            self.topic_list.setCurrentRow(row)

    def _follow_link(self, url: QUrl):
        if url.scheme() == "help":
            self.select_topic(url.path())
