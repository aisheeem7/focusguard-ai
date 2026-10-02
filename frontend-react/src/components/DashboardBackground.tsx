import { VIDEO_SRC } from '@/components/VideoBackground'

// The dashboard's own backdrop (see frontend/css/dashboard.css): the same
// ambient loop as the landing page but under a much heavier overlay, with
// a soft lavender wash at the top and two faint glows - so pages reached
// from the dashboard (Profile) feel like part of it, not the sign-in flow.
export function DashboardBackground() {
  return (
    <>
      <video
        autoPlay
        loop
        muted
        playsInline
        aria-hidden="true"
        className="fixed inset-0 z-0 h-full w-full object-cover motion-reduce:hidden"
      >
        <source src={VIDEO_SRC} type="video/mp4" />
      </video>
      <div
        aria-hidden="true"
        className="fixed inset-0 z-[1]"
        style={{
          background:
            'radial-gradient(ellipse at top, rgba(154, 128, 217, 0.10), transparent 60%), rgba(10, 8, 18, 0.93)',
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none fixed -top-[25vmax] -right-[15vmax] z-[1] h-[60vmax] w-[60vmax] rounded-full blur-[40px]"
        style={{ background: 'radial-gradient(circle, rgba(154, 128, 217, 0.16) 0%, transparent 65%)' }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none fixed -bottom-[30vmax] -left-[10vmax] z-[1] h-[60vmax] w-[60vmax] rounded-full blur-[40px]"
        style={{ background: 'radial-gradient(circle, rgba(127, 199, 170, 0.06) 0%, transparent 65%)' }}
      />
    </>
  )
}
