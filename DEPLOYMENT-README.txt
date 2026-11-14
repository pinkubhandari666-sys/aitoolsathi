AI TOOL SAATHI SEO DEPLOYMENT

1. Upload the CONTENTS of this folder to your Netlify publish root (not as a nested subfolder).
2. Keep index.html at the website root. This is your homepage.
3. Each tool has its own clean URL, such as /jpg-to-pdf/ and /compress-pdf/.
4. sitemap.xml and robots.txt are included at the root.
5. After deployment, submit https://aitoolsathi.in/sitemap.xml in Google Search Console.
6. Use URL Inspection for key pages and request indexing. Google controls indexing and ranking; first position cannot be guaranteed.
7. Existing Google Analytics and Firebase Authentication settings are preserved. Firestore database features are not added by this SEO update.

Dedicated tool pages: 34
Homepage: /

PDF Text Mover has its own SEO page:
https://aitoolsathi.in/pdf-text-mover/
Its canonical URL and Open Graph URL both point to this dedicated page. The page uses the existing homepage tool engine; sitemap.xml includes the new URL.


CONTACT / ADSENSE INFORMATION
Contact email configured: pinkubhandari666@gmail.com

Standalone information pages included:
- /about-us/
- /contact-us/
- /privacy-policy/
- /terms-and-conditions/
- /disclaimer/

AdSense script status:
- The AdSense loader script is present in all 42 HTML pages.
- Publisher ID found in the script: ca-pub-3773073955353988
- This confirms that the code is present in the files; it does NOT confirm that the AdSense account or site is approved.
- ads.txt is not included in this package. Add the exact ads.txt record supplied/confirmed in the AdSense account when required. Do not assume code presence means ads.txt or account verification is complete.

Before deployment, verify that the publisher ID above belongs to your AdSense account. If it does not, replace it with the ID shown in your own AdSense account.


GEMINI AI WRITER + AI DOCUMENT MAKER (BETA)
1. This package includes a Netlify Function at netlify/functions/gemini-generate.js.
2. In Netlify: Site configuration -> Environment variables -> Add a variable:
   Key: GEMINI_API_KEY
   Value: paste your Gemini API key directly in Netlify (never in HTML/JavaScript or chat).
   Ensure the variable is available to Functions.
3. Save the variable, then trigger a new deploy. The function endpoint is:
   /.netlify/functions/gemini-generate
4. AI Writer and AI Document Maker call Gemini server-side. The API key is not sent to the browser.
5. DOCX export is generated in the browser. “Print / Save PDF” opens the print dialog; choose “Save as PDF”.
6. The function currently has a lightweight per-instance IP throttle and prompt length limit. This is not a complete subscription/credit system. Before selling public access, add Firebase Authentication and persistent Firestore credit checks/rate limits.
7. Gemini model configured: gemini-3.8-flash. Model availability and free-tier limits are controlled by Google and may change.
