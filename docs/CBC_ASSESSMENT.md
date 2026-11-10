# CBC competency assessment

Part of the `exams` module. Exams and report cards still handle marks, means and positions. This part handles CBC assessment, which records what a learner can do and never ranks learners.

## Set up (once)

1. **CBC Settings**: choose the rubric.
   * **4-level**: EE / ME / AE / BE (Exceeding, Meeting, Approaching, Below Expectations). This is the default.
   * **8-level**: EE1 to BE2, for schools reporting on the finer scale.

   Each assessment remembers the rubric it was made with. Changing the setting later only affects new assessments and progress reports.

   You can also edit the SMS parents get when a report is published, and the footer printed on the report.
2. **CBC Strands**: one per learning area (a Subject) and grade, with its sub-strands and learning outcomes. Heads of Department can maintain these.

## Assess (teachers, any time in the term)

**Competency Assessment** → pick the term, stream, learning area, strand and (optionally) the sub-strand and how you assessed (observation, oral, project...).

* Click **Get Learners**, then choose each learner's level.
* **Fill Blank Levels** gives everyone not yet levelled the same level, which you can then adjust.
* Leave a level blank if a learner was not assessed.
* Add a short comment where useful, then **Submit**.

Only learners in the stream can be listed, each only once, and only with levels from the assessment's rubric.

## Progress reports (end of term)

**CBC Progress Report** list → **Generate for a Term** (all streams, or one).

How the level for each learning area is worked out:
* All the strand assessments are averaged per strand, so a strand assessed five times doesn't outweigh one assessed once.
* The strands are then averaged for the learning area.
* The average is turned back into a level, with halves rounding up: 3.5 is EE, 3.49 is ME.

The report also lists the learner's strongest learning areas and the ones to work on. It has no marks, means or positions.

Teachers add comments and remarks on each report. Generating again picks up new assessments and keeps comments already typed.

**Publish for a Term** makes the reports visible on the parent portal's **CBC Progress** tab, with a PDF. If the messaging module is on, parents also get an SMS.

## Report

The **CBC Assessment Summary** counts judgements at each level and the share meeting expectations or above. You can group it by learning area, strand or stream, and filter by term, grade or stream.
