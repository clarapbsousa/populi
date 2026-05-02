export default function Footer() {
  return (
    <footer className="bg-[#F9F6F2] text-stone-900 border-t-4 border-stone-900 w-full py-12 px-8 flex flex-col md:flex-row justify-between items-center gap-6">
      <div className="flex flex-col items-center md:items-start gap-2">
        <div className="font-headline font-bold text-lg text-stone-900">
          Azulejo Político
        </div>
        <p className="font-headline text-sm uppercase tracking-widest text-stone-600">
          © 2026 Azulejo Político. Crafting the Civic Mosaic piece by piece.
        </p>
      </div>
      <nav className="flex gap-8">
        <a
          className="font-headline text-sm uppercase tracking-widest text-stone-600 hover:text-primary transition-all focus:outline-none focus:ring-2 focus:ring-primary"
          href="/tradition"
        >
          The Tradition
        </a>
        <a
          className="font-headline text-sm uppercase tracking-widest text-stone-600 hover:text-primary transition-all focus:outline-none focus:ring-2 focus:ring-primary"
          href="/grout-rules"
        >
          Grout Rules
        </a>
        <a
          className="font-headline text-sm uppercase tracking-widest text-stone-600 hover:text-primary transition-all focus:outline-none focus:ring-2 focus:ring-primary"
          href="/privacy"
        >
          Privacy Tile
        </a>
        <a
          className="font-headline text-sm uppercase tracking-widest text-stone-600 hover:text-primary transition-all focus:outline-none focus:ring-2 focus:ring-primary"
          href="/contact"
        >
          Contact
        </a>
      </nav>
    </footer>
  );
}
