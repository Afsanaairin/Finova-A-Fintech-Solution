# Login hero photograph

Asset: `static/login-hero.webp`

Source: user-supplied `images/login_page.png` (526 × 255 pixels). The original is preserved. The source is encoded as WebP for the website without resizing or editing the composition; CSS handles the crop and overlay.

The layout is inspired by [Onehub's client portal page](https://www.onehub.com/solutions/client-portal): a photographic hero, an upper-left brand, centered left-aligned copy, and a dark diagonal overlay. FINOVA retains its white login area and original 440-pixel login card on desktop, with the existing email-code authentication flow.

The decorative image uses `object-fit: cover` to fill the hero, with `object-position: 22% center` to keep the hand and calculator visible at narrow aspect ratios. The overlay is a separate CSS pseudo-element, and all branding, text and controls remain accessible HTML. On phones the hero and login card stack vertically, and the hero link moves focus to the email field. The photo uses FINOVA's existing public static asset route; no external image service or additional public filesystem routes are needed.
