# PHI checklist: HHS Safe Harbor 18 identifiers

This is the canonical list of 18 identifiers that must be removed from data for it to qualify as de-identified under the HIPAA Privacy Rule's Safe Harbor method (45 CFR § 164.514(b)(2)). The list and de-identification standard are issued by the U.S. Department of Health and Human Services (HHS) Office for Civil Rights.

Reference (read if needed for edge cases):
- HHS Guidance: https://www.hhs.gov/hipaa/for-professionals/special-topics/de-identification/index.html
- 45 CFR § 164.514(b) — the regulatory text

**Important framing.** Safe Harbor is a *rules-based checklist*, not a guarantee. A dataset that passes Safe Harbor can still be re-identifiable in small populations or when linked with external data. The HHS standard also requires that the covered entity have *no actual knowledge* that the remaining information could identify an individual. Treat that as a separate question after the 18-item scan.

For OpenH-RF, public release means we apply Safe Harbor strictly. If a contributor wants to retain something Safe Harbor removes (e.g., month of service), that requires the Expert Determination pathway, which is out of scope for automated evaluation — flag for steering-group review.

## The 18 identifiers

Scan everywhere strings or numbers appear — data card prose, zea file attributes, file/group/dataset names, any string-valued data fields, and embedded file metadata.

| # | Category | What to look for |
|---|---|---|
| 1 | **Names** | Full names, first/last, initials, nicknames, maiden names. Also names of relatives, employers, or household members of the subject. |
| 2 | **Geographic subdivisions smaller than a state** | Street address, city, county, precinct, ZIP code. ZIP3 is allowed *only* if the combined population of the ZIP3 area is >20,000 and certain low-population ZIP3s are replaced with 000. Anything finer than ZIP3 is out. |
| 3 | **Dates (except year) related to an individual** | Birth date, admission/discharge dates, date of death, appointment timestamps, exact times. *Year alone is OK.* For ages over 89, aggregate as "90 or older" — exact age 90+ is itself an identifier. |
| 4 | **Telephone numbers** | Any phone number format. |
| 5 | **Fax numbers** | Yes, still on the list. |
| 6 | **Email addresses** | Any email, including institutional ones tied to an individual subject. |
| 7 | **Social Security numbers** | Any portion, full or partial. |
| 8 | **Medical record numbers (MRN)** | Hospital MRNs, EHR patient IDs. Watch for fields named `subject_id`, `patient_id`, `record_id` that contain MRN-format values. |
| 9 | **Health plan beneficiary numbers** | Insurance member IDs. |
| 10 | **Account numbers** | Billing/account numbers tied to the patient. |
| 11 | **Certificate / license numbers** | Driver's license, professional licenses. |
| 12 | **Vehicle identifiers and serial numbers** | License plates, VINs. |
| 13 | **Device identifiers and serial numbers** | Implant serial numbers, pacemaker IDs, *and (relevant here) probe/scanner serial numbers if they can be linked back to an individual scan session.* See note below. |
| 14 | **URLs** | Web addresses, especially patient-portal URLs or links containing tokens. |
| 15 | **IP addresses** | IPv4/IPv6 in any embedded metadata. |
| 16 | **Biometric identifiers** | Fingerprints, voice prints, retinal scans. *Includes voice recordings that could be voice-printed.* |
| 17 | **Full-face photographs and comparable images** | Any image that could identify the subject by face. Relevant to OpenH-RF only if image-of-acquisition material is bundled — channel data itself is fine. |
| 18 | **Any other unique identifying number, characteristic, or code** | The catch-all. Custom study codes, internal tokens, novel ID schemes. *When in doubt, treat conservatively.* |

## Things that frequently appear in zea files and warrant attention

- `subject_id`, `patient_id`, `study_id` — check the *values*, not just the names. If they're sequential integers (subject_001 … subject_042), that's fine. If they're MRN-format, that's identifier #8.
- `acquisition_datetime` — must be truncated to year only (or removed) for human data, per identifier #3.
- `operator_name`, `sonographer` — not subject identifiers, but identifier #1 still applies if a relative or household member of the subject. Generally these should be removed or replaced with role labels.
- Device serial numbers — identifier #13 applies only if traceable to an individual scan session. Model name + general probe info is fine; specific serial numbers should be evaluated.
- Filenames — strip identifiers from filenames too. `scan_jsmith_20240603.hdf5` triggers identifiers #1 and #3.

## Re-identification codes

A "re-identification code" (an internal token the contributor can use to link back to the original record) is **permitted** under Safe Harbor *only if*:
1. The code is not derived from any of the 18 identifiers (no hashes of names, no encrypted SSNs)
2. The mapping is kept by the contributor and not disclosed

If a submission includes obviously-tokenized subject IDs (e.g., random UUIDs), that's fine — note that the contributor must not include the mapping table in the public release.

## What to do when triggered

Per the protocol in `dimensions/07-ethics.md`:
1. Mark the finding as a `blocker`
2. Record the location (file, group, attribute path) and the identifier category — *never the offending value itself*
3. Recommend re-export with the offending field removed, tokenized, or generalized (e.g., dates → year only)
