import pikepdf
from pikepdf import Dictionary, Name


def line(words, size=12, grey=0, x=72, y=700):
    level = grey / 255
    return f"BT /F1 {size} Tf {level:.4f} {level:.4f} {level:.4f} rg {x} {y} Td ({words}) Tj ET\n".encode()


def build(folder, stream=b"", *, name="sample.pdf", title=None, xmp_title=None, lang=None, marked=False, tree=False, links=()):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))
    font = pdf.make_indirect(Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
    image = pdf.make_stream(bytes([200, 200, 200]) * 4)
    image.Type = Name.XObject
    image.Subtype = Name.Image
    image.Width = 2
    image.Height = 2
    image.ColorSpace = Name.DeviceRGB
    image.BitsPerComponent = 8
    page.obj.Resources = Dictionary(Font=Dictionary(F1=font), XObject=Dictionary(Im0=image))
    page.obj.Contents = pdf.make_stream(stream)
    if links:
        annotations = [
            pdf.make_indirect(
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Link,
                    Rect=list(rectangle),
                    Border=[0, 0, 0],
                    A=Dictionary(S=Name.URI, URI=pikepdf.String("https://www.example.org/")),
                )
            )
            for rectangle in links
        ]
        page.obj.Annots = pikepdf.Array(annotations)
    if title is not None:
        pdf.docinfo[Name.Title] = title
    if xmp_title is not None:
        with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as xmp:
            xmp["dc:title"] = xmp_title
    if lang is not None:
        pdf.Root.Lang = pikepdf.String(lang)
    if marked:
        pdf.Root.MarkInfo = Dictionary(Marked=True)
    if tree:
        pdf.Root.StructTreeRoot = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot))
    path = folder / name
    pdf.save(path)
    return path
