# TapScript Lesson 04: Dynamics and Velocity (Apprentice)

> **Under revision — the notation below is not TapScript.** This lesson was
> generated before the notation existed and describes commands the compiler has
> never had. It is kept, labelled, so the rewrite has a starting point. Do not
> learn from it. See `SHIPPING.md`.

**Concept**  
Dynamics control *how* an object moves over time — not just *where*. Velocity is the rate of change of position (pixels per second). In TapScript, you set an object’s `velocity` vector (x,y) and let the physics engine update its position each frame. Add `damping` (friction) to slow it, or `acceleration` to change velocity gradually. For smooth motion, use `lerp` or `ease` — but raw velocity is the foundation for projectiles, enemies, and particle systems.

**Key properties**  
- `velocity: {x: number, y: number}` — px/frame  
- `damping: number` (0 = no friction, 0.98 = slight, 0.9 = heavy)  
- `maxSpeed: number` — clamps velocity magnitude  

**TapScript Example — Bouncing Orb**  
```text
entity Orb {
  position: {x: 200, y: 100}
  velocity: {x: 3, y: 2}
  damping: 0.99
  maxSpeed: 5

  update(dt) {
    this.position.x += this.velocity.x * dt * 60
    this.position.y += this.velocity.y * dt * 60

    // Bounce off screen edges
    if (this.position.x < 0 || this.position.x > 800) {
      this.velocity.x *= -1
    }
    if (this.position.y < 0 || this.position.y > 600) {
      this.velocity.y *= -1
    }

    // Apply damping (multiply velocity)
    this.velocity.x *= this.damping
    this.velocity.y *= this.damping

    // Clamp speed
    let speed = Math.hypot(this.velocity.x, this.velocity.y)
    if (speed > this.maxSpeed) {
      let scale = this.maxSpeed / speed
      this.velocity.x *= scale
      this.velocity.y *= scale
    }
  }
}
```

**JSON Exercise Block**  
```json
{
  "exercise": "Orb with variable gravity",
  "task": "Create an entity 'Ball' that starts at position (100, 300) with velocity (2, -5). Add a constant downward acceleration of 0.2 per frame. When it hits the bottom (y >= 550), reverse its y-velocity and apply 0.95 damping. Clamp maxSpeed to 8.",
  "
