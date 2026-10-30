# Vision: the cell reads levels and solutions from a picture

**Illustrative prototype.** The drawn test scenes stand for a clean bench; a real camera, real glass and real light must be tried before anyone relies on the readings.

## What it does

A picture of the bench goes in (a sample scene, the computer's camera, or a photo). For every vessel holding a coloured liquid the Vision page says:

- **which solution**, by colour (red, orange, yellow, green, teal, blue, purple, pink);
- **how full** the vessel is, as a percentage;
- **where it stands**, in the arm's own frame (metres), when the four printed markers are in view;
- **whether the arm can reach it** (inside the arm's reach and outside its own column).

Vessels it is unsure of are marked "check", never guessed quietly.

## How it works (plain)

- **Liquids are found by colour.** Any clearly coloured region is a liquid; its top edge is the surface and its width is the vessel's inner width.
- **The level** is the liquid's height divided by the height a full vessel would have, which is the vessel's width times its "shape" (a tall test tube has a larger shape number than a squat vial). The page has a slider for it; set it once by looking at a full vessel.
- **The colour** is the average hue of the liquid, named from a table of hue bands.
- **The position** comes from four printed square markers (ArUco codes 0 to 3) lying on the bench at known places. Seeing all four lets the program work out how the picture maps onto the bench, so any point in the picture becomes a position the arm can go to.

There are two readers, and the page lets you choose:

- **Colour rules** (classic image processing with OpenCV): no training, no data, easy to explain.
- **Trained model** (added 2026-10-23, see below): a small neural network that marks, in a picture, which pixels are a vessel and which are its contents, so it also sees pale and colourless liquids and does not need the vessel-shape setting tuned so carefully.

Neither needs the internet to run.

## What it cannot do (so nobody is surprised)

- **Colourless liquids are invisible** to it (water). Use coloured solutions, or add a dye.
- **An empty vessel is not found.** There is nothing coloured to see.
- **A very small amount** (below about 5% in the sample scenes) is not seen.
- **The level is an estimate** to a few percent, against the vessel shape that was set. The balance is the right instrument for exact amounts; vision confirms and cross-checks.
- **A vessel hidden behind another, or a marker covered by a vessel,** cannot be read: keep markers clear of the vessels' tall shapes.
- Light, background and camera position matter more than the program does: plain background, even light, camera still.

## How well it reads the test scenes (known answers)

On drawn scenes the levels are within a few percentage points of the truth, all eight colours are told apart, positions are found to a few millimetres, and the arm's reach is judged correctly (`check_vision.bat`). Dim light, noise and a little blur are tolerated. This is a check of the program against pictures whose answers are known; it is **not** a claim about real photographs.

## The trained model

- **What it is.** A small segmentation network (MobileNetV3, 3 million numbers) that labels every pixel as background, vessel or the contents of a vessel. The level is the contents' height over the vessel's height (a "full" vessel reads about 78%, set by the page's slider); the solution is named from the colour of the contents; the position comes from the markers, as before.
- **How it was trained.** `tools\download_labpics.py` fetched the public **LabPics v1** dataset (Sagi Eppel, Zenodo record 3697452, **MIT licence**): 2,187 real photographs of liquids and solids in vessels, each vessel and its filled part outlined by hand. `tools\train_vision.py` fine-tuned a network that already knew everyday photographs, on **1,669 of those photographs plus 500 drawn bench scenes** (with exact labels), for 12 passes, in **53.7 minutes on this computer's processor** (no graphics card). The weights are in `data\vision_models` (not saved in git; run the training again to recreate them).
- **How well it does, on pictures it never saw** (IoU: the overlap of its mask with the hand-drawn one; 1.0 is perfect):

| | Vessel | Contents |
|---|---|---|
| 497 unseen real photographs (LabPics test set) | 0.70 | 0.71 |
| 60 unseen drawn bench scenes | 0.54 | 0.54 |

  On the drawn scenes, the level it reads is off by **3.7 percentage points on average (97% within 10 points)** against the level worked out from the exact labels.
- **What it does well.** It finds every vessel in the sample scenes, names the solution correctly, reads the five ingredient bottles in the cell's vision check, and reads the example test tube (a pale liquid the colour rules marked "check") with high confidence.
- **What it does not do well.** Very small amounts (below about 15%) are not seen (the colour rules see down to about 5%); the level of a nearly full vessel is a few points low because the vessel's cap and glass bottom count as part of its height; it was trained on LabPics-style photographs and drawn scenes, so a different camera, glass or lighting may read worse, and the right way to find out is to try it on your own photographs.
- **Honest limits of the training.** This is a small network trained once, for about an hour, on a laptop processor. It is a working prototype of a trained reader, not a tuned product. The overlap scores are respectable for a model this size but not state of the art.

## In the live run

When the arm picks up an ingredient bottle in the **Live run** page, a **Vision check** card appears under the picture: a photograph of that bottle (drawn, since the simulation has no camera), the reading (which solution, how full), and the verdict, **right bottle** or **wrong bottle**, against the solution the plan expected (drug blue, filler yellow, binder green, disintegrant orange, lubricant purple). The reading is done by the trained model.

**The stickers are the identity, the colour is the second look.** Colour alone cannot tell two ingredients apart, so each bottle carries two stickers: a **name sticker** (the ingredient's name in capitals) and a **barcode sticker** (an EAN-13, the common 13-digit product barcode, with the bottle's own ID). The check **scans the barcode** with a standard barcode reader and **reads the name** with a text-reading model (a PP-OCRv3 text finder and a CRNN text reader, both run by OpenCV; downloaded once by `tools\download_ocr_models.py`; Apache-2.0 models from OpenCV's collection). **Either one identifies the bottle** when the other cannot be read; when both are read they must agree. Overall answer: **right bottle** (the stickers say the planned bottle and the liquid is as expected), **wrong bottle** (they say another ingredient, even if the liquid is the right colour), **check bottle** (the barcode and the name disagree, or the stickers are right but the liquid is not), **label not read** (neither can be read: never accepted). The barcode reader checks the barcode's check digit, so a damaged barcode is refused, not guessed; a name that is a letter or two off is still taken for the right name, and writing that is not one of the cell's five names (for example a caption in the photograph) is not taken for one. The simulation puts the stickers onto the photograph, on the bottle (paper stickers that follow the curve of the glass, with shaded edges and a soft shadow); on a real cell the camera would read real stickers, and lighting, glare, curved glass and wear would make that harder than it is here. Without the text models the bottle is identified by its barcode alone. OpenCV's barcode reader handles the EAN and UPC families only: if the real bottles carry Code 128 or Data Matrix, another reader has to be added (with approval).

**Laid out for a demo.** The Live run page has the vision check as its own panel beside the cell: the camera's photograph, the barcode read against the barcode expected, the liquid's colour and level, and one verdict. The stage and the panel flash a green frame for a right bottle, red for a wrong one, amber for "check" and blue while the camera is looking. A "Show the camera" choice in the page's top bar lets the presenter show the camera, for the next bottle picked up, a wrong bottle, an unreadable barcode (the name still identifies the bottle), a bottle with no stickers or a liquid that does not match, or a defective tablet for the next tablet (marked on the page as a demonstration; the run itself is unchanged).
## The tablet inspection (second place the cell uses vision)

When the arm lifts the pressed tablet out of the die (action A033 of every trial) the cell's camera inspects it: **tablet ok** (it goes on to the hardness gauge) or **defective tablet** (chipped, cracked, worn, discoloured or broken: it would be sent to the discard bin). When it calls a tablet defective it outlines, in red, the part of the photograph that made it say so. This is the "inspect and divert" step of the use case, and it is the one place in a trial where an instrument cannot tell the answer: the hardness gauge gives a number but cannot see a chip.

- **How it works.** A MobileNetV3-Large network (the same family as the liquid reader), fine-tuned by `tools\train_tablet.py` on the public **PharmaVision** photographs: 640 smartphone photographs of tablets (380 to train on, 60 to choose the best pass, 200 kept back to test). It is a classifier, not an object detector: the camera in the cell sees one tablet at a time, so there is nothing to find. A detector such as YOLO is for finding many objects in one picture (for example counting tablets on a tray); it would also bring a licence question (Ultralytics' YOLO is AGPL-3.0 and its owner asks for a paid licence for commercial or internal use) and a new library.
- **How well it does, on the 200 test photographs it never saw** (read through the app's own path): **83.5% right**; it finds **68% of the defective tablets** (68 of 100) and passes **99% of the normal ones** (1 false alarm in 100); ranking score (AUC) 0.92. The threshold (0.5) was fixed before any result existed. Lowering it finds more defective tablets and raises false alarms (on the test photographs: 0.3 finds 76% with 1 false alarm, 0.2 finds 82% with 8, 0.1 finds 89% with 28); the table is in `data\vision_models\tablet_report.json`, as information for a decision and not a tuning. **Missing about a third of defective tablets is not good enough for a real line**: it is what a small public dataset gives.
- **What the scores do not show.** The same tablet products appear in the training, validation and test photographs, so a tablet the network has never seen would probably score worse. The photographs are smartphone pictures against dark or green cloth, not a camera in a cell with its own lighting. The dataset's own licence text was not readable to me; the project owner confirmed on 2026-10-23 that it may be used, and it is kept out of git and not republished. Its labels say how a tablet looks, not whether it would pass hardness or dissolution.
- **In the live run.** The simulation makes no real tablet, so the photograph is a real test photograph standing in for the camera: a normal tablet, a different one each trial. A presenter can choose "a defective tablet" in the page's **Show the camera** list to see the red case (marked on the page as a demonstration); the run itself is unchanged.
## Data: does it need any?

- **To run the colour rules: no.** They need no training. **The trained model** needed the LabPics photographs once, to train.
- **To test: pictures.** The check uses drawn scenes with a known answer. Photographs dropped into `data/vision_samples` appear in the page's sample list.
- **Public datasets exist** if a learned model is ever needed (for example for clear liquids or messy backgrounds): the Roboflow Universe "liquidlength" and "Glass Level Detection" sets (CC BY 4.0, a free account is needed to download), the ECCV 2024 DTLD dual-transparent-liquid dataset (repository and licence not yet confirmed) and LabPics (annotations and some images under CC BY-NC-ND, so not for a commercial setting). LabPics (MIT licence; the version 1 set on Zenodo, the annotations of the later Chemistry set are non-commercial) is the one used for the trained model.
- **One example image** is included (`data/vision_samples/Rendered_test_tube.jpg`, a 3D rendering by M4D GROUP, CC BY 2.0, credited in `ATTRIBUTION.txt`). The program reads it as one blue-teal vessel and marks it "check", which is the honest answer for a pale liquid with bubbles.

## How to try it with a real camera

1. Print the four markers (ids 0 to 3, 4x4 ArUco codes, 6 cm square) and lay them at the corners of a sheet on the bench, at the positions in `cellpoc/vision/config.py` (or change the table there to where yours lie).
2. Put coloured liquids in clear vials on the sheet, with a plain background and even light.
3. Open the Vision page, choose **Camera** and take a picture. Set the shape slider with one full vessel.

## What is not built

- Moving a real arm from these positions (hand-eye calibration of a real arm, grasping). The positions are in the arm's frame and the reach test uses the layout's reach; nothing drives hardware.
- Reading clear liquids, powders and tablets, and a learned model for messy scenes.
