from pptx import presentation


def delete_template_slide(
    prs: presentation.Presentation, count: int = 1
) -> presentation.Presentation:
    slide_id_list = prs.slides._sldIdLst
    for slide_id in list(slide_id_list)[:count]:
        prs.part.drop_rel(slide_id.rId)
        slide_id_list.remove(slide_id)

    return prs
