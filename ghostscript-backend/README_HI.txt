AIToolSathi Combined Backend — PDF + JPEG + Image (Pillow)

Is website package mein ek hi Render backend par PDF aur image compression ke endpoints integrated hain.

BACKEND ENDPOINTS
1) PDF Compressor
   POST /compress
   Form: file (PDF), mode (normal/high), target_kb (optional)
   Engine: Ghostscript
   Note: Existing website PDF compression implementation is preserved.

2) JPEG Compressor
   POST /compress-jpeg
   Form: file (JPG/JPEG), mode (normal/high), target_kb, quality (0=automatic; 1-95=manual),
         max_width, max_height, dpi

3) Compress Image / Image Compressor
   POST /compress-image
   Form: file (JPG, JPEG, PNG, WEBP, BMP, TIFF), mode (normal/high),
         target_kb, output_format (original/JPG/PNG/WEBP),
         max_width, max_height, dpi, quality (0=automatic; 1-95=manual)

FRONTEND CONNECTION
- Homepage index.html, /jpeg-compressor/, /compress-image/ and /image-compressor/ are connected in code to:
  https://aitoolsathi-pdf-api.onrender.com
- PDF frontend continues to call /compress.
- JPEG Compressor calls /compress-jpeg.
- Compress Image and Image Compressor call /compress-image.
- Browser FormData is used; do not manually set Content-Type.
- If Render assigns a different service URL, update ATS_GHOSTSCRIPT_API and ATS_PILLOW_API in the respective HTML pages.

IMAGE BEHAVIOUR
- Normal and High use separate JPEG/WebP quality ladders.
- PNG is lossless: quality does not apply; optimization and optional resizing are used.
- PNG/WebP transparency is preserved. Converting transparent images to JPEG uses a white background.
- Target size is best-effort, not guaranteed. The API returns X-Target-Reached=false when it cannot meet the requested size.
- The frontend avoids reporting an unmet target as successful.
- BMP/TIFF input is converted to JPEG when output format is Original because those formats are not output targets.
- Maximum upload defaults to 30 MB; set MAX_UPLOAD_MB on Render to change it.
- MAX_IMAGE_PIXELS defaults to 40 million pixels to reduce decompression-bomb risk.

DEPLOY
1) Upload the complete website ZIP contents to the GitHub repository root.
2) Render Dashboard > New > Blueprint; select that repository.
3) Render reads root render.yaml; its rootDir is ghostscript-backend.
4) Deploy and wait for the service to finish.
5) Open /health on the Render service. Expected: engines.ghostscript=true and engines.pillow=true.
6) Open / to see the service and endpoint list.
7) Then test PDF, JPEG, Compress Image and Image Compressor from the deployed website.

IMPORTANT
- Frontend code is connected to the default Render URL, but a live deployment and browser end-to-end test still need to be completed by you after deployment.
- If the service URL differs, update the API constants in HTML.
