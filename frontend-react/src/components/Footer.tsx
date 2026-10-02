/* Decorative signature line, not meaningful UI text - the ৎ/୨ glyphs are
   a stylistic flourish, not actual Bengali words, so this stays identical
   across languages rather than being "translated" into something that
   would misrepresent it. Shared by every page (the dashboard's app.html
   renders the same line as .app-footer). */
export function Footer() {
  return (
    <footer className="animate-fade-rise-delay-2 px-3 py-6 text-center font-sans text-sm text-muted-foreground">
      ୨ৎ made with ♡ by ash ୨ৎ
    </footer>
  )
}
