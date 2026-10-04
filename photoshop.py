"""
photoshop.py — Photoshop automation via ExtendScript (DoJavaScript).

All operations run through Photoshop's internal JavaScript engine via COM,
which is the most reliable way to suppress dialogs and run fully unattended.
"""

import os
import win32com.client


class PhotoshopError(Exception):
    """Raised when a Photoshop automation step fails."""
    pass


def ensure_photoshop():
    """Connect to an already-running Photoshop. Does NOT launch it — the user
    opens Photoshop themselves. Raises PhotoshopError if it isn't running."""
    try:
        return win32com.client.GetActiveObject("Photoshop.Application")
    except Exception:
        raise PhotoshopError(
            "Photoshop is not running. Please open Adobe Photoshop, then try again."
        )


def _get_app():
    """Connect to the running Photoshop and suppress dialogs."""
    app = ensure_photoshop()
    app.DoJavaScript('app.displayDialogs = DialogModes.NO;')
    return app


def _jsx(app, script):
    """Run an ExtendScript snippet inside Photoshop. Returns the result string."""
    return app.DoJavaScript(script)


# Shared ExtendScript helper. Currently used by render_fill_plate; the older
# process_mockup / process_mockup_artwork keep their own inline copies.
_JS_FINDLAYER = r'''
function findLayer(c, n) {
  for (var i = 0; i < c.artLayers.length; i++) {
    if (c.artLayers[i].name.toLowerCase() == n.toLowerCase()) return c.artLayers[i];
  }
  for (var j = 0; j < c.layerSets.length; j++) {
    var f = findLayer(c.layerSets[j], n);
    if (f !== null) return f;
  }
  return null;
}
'''


def process_mockup(psd_path, logo_path, bg_color, output_path, fill_fraction=0.80):
    """
    Full automated pipeline for one PSD template.

    Opens the PSD, finds the 'artwork' smart object, fills it with bg_color,
    places the logo centered at fill_fraction of the layer (default 80%),
    saves as JPG, closes without saving.
    """
    # Normalize all paths to Windows backslash format
    psd_path = str(os.path.abspath(psd_path)).replace("\\", "/")
    logo_path = str(os.path.abspath(logo_path)).replace("\\", "/")
    output_path = str(os.path.abspath(output_path)).replace("\\", "/")

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path.replace("/", "\\"))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Parse background color
    hex_color = bg_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Build the full ExtendScript to run inside Photoshop
    script = f"""
    // Suppress all dialogs
    app.displayDialogs = DialogModes.NO;

    // 1. Open the PSD file
    var psdFile = new File("{psd_path}");
    var doc = app.open(psdFile);

    // 2. Find the 'artwork' layer (recursive search)
    function findLayer(container, name) {{
        // Search art layers
        for (var i = 0; i < container.artLayers.length; i++) {{
            if (container.artLayers[i].name.toLowerCase() === name.toLowerCase()) {{
                return container.artLayers[i];
            }}
        }}
        // Search layer sets (groups)
        for (var j = 0; j < container.layerSets.length; j++) {{
            var found = findLayer(container.layerSets[j], name);
            if (found !== null) return found;
        }}
        return null;
    }}

    var artwork = findLayer(doc, "artwork");
    if (artwork === null) {{
        doc.close(SaveOptions.DONOTSAVECHANGES);
        throw new Error("No layer named artwork found");
    }}

    // 3. Verify it is a Smart Object
    if (artwork.kind !== LayerKind.SMARTOBJECT) {{
        doc.close(SaveOptions.DONOTSAVECHANGES);
        throw new Error("artwork layer is not a Smart Object");
    }}

    // 4. Open the Smart Object for editing
    doc.activeLayer = artwork;
    executeAction(stringIDToTypeID("placedLayerEditContents"),
                  new ActionDescriptor(), DialogModes.NO);

    var soDoc = app.activeDocument;

    // 5. Fill with background color
    var fillColor = new SolidColor();
    fillColor.rgb.red = {r};
    fillColor.rgb.green = {g};
    fillColor.rgb.blue = {b};
    soDoc.selection.selectAll();
    soDoc.selection.fill(fillColor, ColorBlendMode.NORMAL, 100, false);
    soDoc.selection.deselect();

    // 6. Place the logo
    var logoFile = new File("{logo_path}");
    var placeDesc = new ActionDescriptor();
    placeDesc.putPath(charIDToTypeID("null"), logoFile);
    executeAction(charIDToTypeID("Plc "), placeDesc, DialogModes.NO);

    // The placed layer is now active — resize and center it
    var placed = soDoc.activeLayer;
    var soW = soDoc.width.as("px");
    var soH = soDoc.height.as("px");

    var bounds = placed.bounds;
    var layerW = bounds[2].as("px") - bounds[0].as("px");
    var layerH = bounds[3].as("px") - bounds[1].as("px");

    // Scale to fill_fraction, preserving aspect ratio
    var targetW = soW * {fill_fraction};
    var targetH = soH * {fill_fraction};
    var scale = Math.min(targetW / layerW, targetH / layerH);
    var scalePct = scale * 100.0;

    placed.resize(scalePct, scalePct, AnchorPosition.MIDDLECENTER);

    // Re-read bounds and center
    bounds = placed.bounds;
    var curCX = (bounds[0].as("px") + bounds[2].as("px")) / 2.0;
    var curCY = (bounds[1].as("px") + bounds[3].as("px")) / 2.0;
    placed.translate(soW / 2.0 - curCX, soH / 2.0 - curCY);

    // 7. Flatten smart object and save/close it
    soDoc.flatten();
    soDoc.save();
    soDoc.close();

    // 8. Back in parent PSD — flatten and save as JPG
    app.activeDocument.flatten();

    var jpgFile = new File("{output_path}");
    var jpgOpts = new JPEGSaveOptions();
    jpgOpts.quality = 10;
    jpgOpts.formatOptions = FormatOptions.STANDARDBASELINE;
    jpgOpts.embedColorProfile = true;
    app.activeDocument.saveAs(jpgFile, jpgOpts, true, Extension.LOWERCASE);

    // 9. Close without saving the original PSD
    app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);

    "OK";
    """

    try:
        app = _get_app()
        result = _jsx(app, script)
    except Exception as exc:
        # Try to clean up any open documents on failure
        try:
            app = win32com.client.Dispatch("Photoshop.Application")
            while app.Documents.Count > 0:
                app.ActiveDocument.Close(2)
        except Exception:
            pass
        raise PhotoshopError(f"Mockup generation failed for {psd_path}: {exc}") from exc


def process_mockup_artwork(psd_path, artwork_path, output_path):
    """
    Artwork-mode pipeline: place the artwork to fully cover the 'artwork'
    smart object layer (stretched to fit, no background fill), save as JPG.
    """
    psd_path = str(os.path.abspath(psd_path)).replace("\\", "/")
    artwork_path = str(os.path.abspath(artwork_path)).replace("\\", "/")
    output_path = str(os.path.abspath(output_path)).replace("\\", "/")

    output_dir = os.path.dirname(output_path.replace("/", "\\"))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    script = f"""
    app.displayDialogs = DialogModes.NO;

    var psdFile = new File("{psd_path}");
    var doc = app.open(psdFile);

    function findLayer(container, name) {{
        for (var i = 0; i < container.artLayers.length; i++) {{
            if (container.artLayers[i].name.toLowerCase() === name.toLowerCase()) {{
                return container.artLayers[i];
            }}
        }}
        for (var j = 0; j < container.layerSets.length; j++) {{
            var found = findLayer(container.layerSets[j], name);
            if (found !== null) return found;
        }}
        return null;
    }}

    var artwork = findLayer(doc, "artwork");
    if (artwork === null) {{
        doc.close(SaveOptions.DONOTSAVECHANGES);
        throw new Error("No layer named artwork found");
    }}
    if (artwork.kind !== LayerKind.SMARTOBJECT) {{
        doc.close(SaveOptions.DONOTSAVECHANGES);
        throw new Error("artwork layer is not a Smart Object");
    }}

    // Open Smart Object for editing
    doc.activeLayer = artwork;
    executeAction(stringIDToTypeID("placedLayerEditContents"),
                  new ActionDescriptor(), DialogModes.NO);

    var soDoc = app.activeDocument;
    var soW = soDoc.width.as("px");
    var soH = soDoc.height.as("px");

    // Place the artwork image
    var artFile = new File("{artwork_path}");
    var placeDesc = new ActionDescriptor();
    placeDesc.putPath(charIDToTypeID("null"), artFile);
    executeAction(charIDToTypeID("Plc "), placeDesc, DialogModes.NO);

    var placed = soDoc.activeLayer;
    var bounds = placed.bounds;
    var layerW = bounds[2].as("px") - bounds[0].as("px");
    var layerH = bounds[3].as("px") - bounds[1].as("px");

    // Cover fit: scale uniformly so artwork fully covers the layer.
    // Excess on one axis gets cropped by the smart object's canvas bounds.
    var scale = Math.max(soW / layerW, soH / layerH) * 100.0;
    placed.resize(scale, scale, AnchorPosition.MIDDLECENTER);

    // Center it exactly
    bounds = placed.bounds;
    var curCX = (bounds[0].as("px") + bounds[2].as("px")) / 2.0;
    var curCY = (bounds[1].as("px") + bounds[3].as("px")) / 2.0;
    placed.translate(soW / 2.0 - curCX, soH / 2.0 - curCY);

    soDoc.flatten();
    soDoc.save();
    soDoc.close();

    app.activeDocument.flatten();

    var jpgFile = new File("{output_path}");
    var jpgOpts = new JPEGSaveOptions();
    jpgOpts.quality = 10;
    jpgOpts.formatOptions = FormatOptions.STANDARDBASELINE;
    jpgOpts.embedColorProfile = true;
    app.activeDocument.saveAs(jpgFile, jpgOpts, true, Extension.LOWERCASE);

    app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
    "OK";
    """

    try:
        app = _get_app()
        _jsx(app, script)
    except Exception as exc:
        try:
            app = win32com.client.Dispatch("Photoshop.Application")
            while app.Documents.Count > 0:
                app.ActiveDocument.Close(2)
        except Exception:
            pass
        raise PhotoshopError(f"Artwork mockup failed for {psd_path}: {exc}") from exc


def render_fill_plate(psd_path, rgb, out_png):
    """Open PSD, fill the 'artwork' smart object solid `rgb`, flatten, save PNG,
    close without modifying the source. Used to build marker/background plates."""
    psd = str(os.path.abspath(psd_path)).replace("\\", "/")
    out = str(os.path.abspath(out_png)).replace("\\", "/")
    # Clamp to valid 0-255 integers before injecting into the ExtendScript.
    r, g, b = (int(max(0, min(255, v))) for v in rgb)

    out_dir = os.path.dirname(os.path.abspath(out_png))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    script = _JS_FINDLAYER + f'''
    app.displayDialogs = DialogModes.NO;
    var doc = app.open(new File("{psd}"));
    var art = findLayer(doc, "artwork");
    if (art === null) {{ doc.close(SaveOptions.DONOTSAVECHANGES); throw new Error("No layer named artwork found"); }}
    if (art.kind != LayerKind.SMARTOBJECT) {{ doc.close(SaveOptions.DONOTSAVECHANGES); throw new Error("artwork layer is not a Smart Object"); }}
    doc.activeLayer = art;
    executeAction(stringIDToTypeID("placedLayerEditContents"), new ActionDescriptor(), DialogModes.NO);
    var so = app.activeDocument;
    var col = new SolidColor(); col.rgb.red = {r}; col.rgb.green = {g}; col.rgb.blue = {b};
    so.selection.selectAll();
    so.selection.fill(col, ColorBlendMode.NORMAL, 100, false);
    so.selection.deselect();
    so.flatten(); so.save(); so.close();
    app.activeDocument.flatten();
    app.activeDocument.saveAs(new File("{out}"), new PNGSaveOptions(), true, Extension.LOWERCASE);
    app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);
    "OK";
    '''
    try:
        app = _get_app()
        _jsx(app, script)
    except Exception as exc:
        try:
            app = win32com.client.Dispatch("Photoshop.Application")
            while app.Documents.Count > 0:
                app.ActiveDocument.Close(2)
        except Exception:
            pass
        raise PhotoshopError(f"Plate render failed for {psd}: {exc}") from exc
    if not os.path.exists(out_png):
        raise PhotoshopError(f"Plate not written: {out_png}")
