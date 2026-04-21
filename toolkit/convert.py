"""Converts PDF and MHTML sources into DOCX using Microsoft Word automation."""

import os
import sys
import pythoncom
import win32com.client as win32

_WD_FORMAT_DOCX = 12  # Word XML Document (.docx)


def pdf_to_docx(input_path, output_path=None, visible=False):
    pythoncom.CoInitialize()
    input_path = os.path.abspath(input_path)
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".docx"
    output_path = os.path.abspath(output_path)

    word = win32.DispatchEx("Word.Application")
    word.Visible = visible
    word.DisplayAlerts = 0  # Suppress PDF conversion confirmation dialog
    doc = None
    try:
        doc = word.Documents.Open(input_path, ConfirmConversions=False)
        doc.SaveAs(output_path, FileFormat=_WD_FORMAT_DOCX)
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
        pythoncom.CoUninitialize()


def mhtml_to_docx(input_path, output_path=None, visible=False):
    pythoncom.CoInitialize()
    input_path = os.path.abspath(input_path)
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".docx"
    output_path = os.path.abspath(output_path)

    # Use an isolated Word instance so we do not attach to/close user-open Word windows.
    word = win32.DispatchEx("Word.Application")
    word.Visible = visible
    doc = None
    try:
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=_WD_FORMAT_DOCX)
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
        pythoncom.CoUninitialize()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert.py input.mhtml [output.docx]")
        sys.exit(1)
    mhtml_to_docx(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)