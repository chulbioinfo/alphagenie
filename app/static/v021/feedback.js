// No feedback upload, analytics or third-party widgets in the local edition.
export function createFeedbackController(){
  return {busy:false,closeEditor(){},async enter(){
    document.querySelector('#feedbackView').innerHTML=`<section class="figure-card"><h2>Feedback & support</h2><p>This local edition does not send feedback, API keys, usage events or analysis results to AlphaGENIE operators.</p><p>To report a problem, use the Issues tab of the GitHub repository from which you downloaded this package. Nothing is uploaded automatically.</p><details><summary>Before sharing a report</summary><p>Remove API keys, patient information, private variants, local file paths and raw logs. Use a minimal, synthetic example. Do not paste credentials into an issue.</p></details></section>`;
  }};
}
