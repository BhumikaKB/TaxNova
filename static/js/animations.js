/**
 * TaxNova shared animation utilities.
 * Kept dependency-free (no animation library) since these are two
 * small, well-understood effects - a count-up and a confetti burst -
 * used only where they mean something (a computed tax number
 * resolving, a completed calculation).
 */

function tnAnimateCount(el, target, opts = {}) {
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        el.textContent = tnFormatRupees(target);
        return;
    }

    const duration = opts.duration || 900;
    const prefix = opts.prefix || '₹';
    const start = 0;
    const startTime = performance.now();

    function tick(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        // ease-out cubic - fast start, gentle settle, matches how a
        // "result arriving" should feel rather than a linear ticker
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + (target - start) * eased);
        el.textContent = prefix + current.toLocaleString('en-IN');
        if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

function tnFormatRupees(n) {
    return '₹' + Number(n).toLocaleString('en-IN');
}

function tnFireConfetti(count = 40) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const colors = ['#4f7cff', '#7c3aed', '#f5b942', '#14b8a6'];

    for (let i = 0; i < count; i++) {
        const piece = document.createElement('div');
        piece.className = 'tn-confetti-piece';
        piece.style.left = Math.random() * 100 + 'vw';
        piece.style.background = colors[Math.floor(Math.random() * colors.length)];
        piece.style.animationDuration = (1.6 + Math.random() * 1.2) + 's';
        piece.style.animationDelay = (Math.random() * 0.3) + 's';
        piece.style.width = piece.style.height = (5 + Math.random() * 6) + 'px';
        document.body.appendChild(piece);
        setTimeout(() => piece.remove(), 3200);
    }
}
