"""Converts PDF and MHTML sources into DOCX using Microsoft Word automation."""

import os
import sys
import win32com.client as win32


def pdf_to_docx(input_path, output_path=None, visible=False):
    input_path = os.path.abspath(input_path)
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".docx"
    output_path = os.path.abspath(output_path)

    wdFormatXMLDocument = 12  # .docx

    word = win32.DispatchEx("Word.Application")
    word.Visible = visible
    word.DisplayAlerts = 0  # Suppress PDF conversion confirmation dialog
    doc = None
    try:
        doc = word.Documents.Open(input_path, ConfirmConversions=False)
        doc.SaveAs(output_path, FileFormat=wdFormatXMLDocument)
        print(f"Saved: {output_path}")
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        try:
            word.DisplayAlerts = 1
            word.Quit()
        except Exception:
            pass


def mhtml_to_docx(input_path, output_path=None, visible=False):
    input_path = os.path.abspath(input_path)
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".docx"
    output_path = os.path.abspath(output_path)

    # Word constants
    wdFormatXMLDocument = 12  # .docx

    # Use an isolated Word instance so we do not attach to/close user-open Word windows.
    word = win32.DispatchEx("Word.Application")
    word.Visible = visible
    doc = None
    try:
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=wdFormatXMLDocument)
        print(f"Saved: {output_path}")
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        try:
            word.Quit()
        except Exception:
            pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert.py input.mhtml [output.docx]")
        sys.exit(1)
    mhtml_to_docx(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)