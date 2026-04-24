import {Composition} from 'remotion';
import {YunYouBaoTutorial} from './YunYouBaoTutorial';

export const RemotionRoot = () => {
  return (
    <Composition
      id="YunYouBaoTutorial"
      component={YunYouBaoTutorial}
      durationInFrames={1440}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
