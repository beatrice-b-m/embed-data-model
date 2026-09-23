"""EMBED image-metadata semantics honoured by the loader."""

from embed_data_model import ImageModality, load_embed


def image_row(**fields):
    row = {
        "anon_dicom_path": "cohort1/P1/S1/SE1/U1.dcm",
        "acc_anon": "A1",
        "empi_anon": "P1",
        "ImageLateralityFinal": "L",
        "ImagesInAcquisition": 60,
    }
    row.update(fields)
    return row


def test_images_in_acquisition_is_the_frame_count_of_a_dbt_image():
    graph = load_embed(images=[image_row(FinalImageType="3D")]).graph

    (image,) = graph.images
    assert image.modality is ImageModality.DBT
    assert image.frame_count == 60


def test_images_in_acquisition_is_not_a_frame_count_for_2d_images():
    graph = load_embed(images=[image_row(FinalImageType="2D")]).graph

    (image,) = graph.images
    assert image.modality is ImageModality.FFDM
    assert image.frame_count is None
