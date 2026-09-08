// Decorative, fixed equations. No model calls or interaction.
const backgroundEquations = [
 String.raw`X(f)=\int_{-\infty}^{\infty}x(t)e^{-i2\pi ft}\,dt`,
 String.raw`A\mathbf v=\lambda\mathbf v`,
 String.raw`e^{i\theta}=\cos\theta+i\sin\theta`,
 String.raw`\nabla\cdot\mathbf B=0`,
 String.raw`m\ddot x+kx=0`,
 String.raw`\mathcal L\{f\}(s)=\int_0^\infty f(t)e^{-st}\,dt`,
 String.raw`\det(A-\lambda I)=0`,
 String.raw`\frac{\partial u}{\partial t}=\alpha\nabla^2u`
];
for(const equation of backgroundEquations){
 const el=document.createElement('div');
 katex.render(equation,el,{displayMode:true,throwOnError:true,output:'html'});
 document.getElementById('equationBackdrop').append(el);
}
