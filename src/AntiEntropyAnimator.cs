using UnityEngine;

namespace AntiEntropyGenerator
{
    /// <summary>
    /// Runtime animation controller: switches between idle and off based on
    /// Operational.IsActive.
    /// </summary>
    public sealed class AntiEntropyAnimator : KMonoBehaviour
    {
        private KBatchedAnimController anim;
        private Operational operational;

        protected override void OnSpawn()
        {
            base.OnSpawn();
            anim = GetComponent<KBatchedAnimController>();
            operational = GetComponent<Operational>();

            if (anim != null)
            {
                bool active = operational != null && operational.IsActive;
                anim.Play(active ? "idle" : "off", KAnim.PlayMode.Loop);
            }

            Subscribe(824508782, OnActiveChanged);
        }

        private void OnActiveChanged(object data)
        {
            if (anim == null)
            {
                return;
            }

            bool active = operational != null && operational.IsActive;
            anim.Play(active ? "idle" : "off", KAnim.PlayMode.Loop);
        }
    }
}
