import os
import unittest
from unittest.mock import patch

os.environ["GEMINI_API_KEY"] = "test-key"

from main import _make_image


class ImageGenerationFallbackTests(unittest.TestCase):
    def test_falls_back_to_gemini_when_hf_model_is_deprecated(self):
        with patch.dict("os.environ", {"HF_TOKEN": "test-token", "HF_IMAGE_MODEL": "stabilityai/stable-diffusion-xl-base-1.0"}, clear=False):
            class FakeResponse:
                status_code = 410
                headers = {"content-type": "application/json"}
                text = '{"error":"The requested model is deprecated and no longer supported by provider hf-inference"}'

                def raise_for_status(self):
                    raise RuntimeError("410 Client Error")

            with patch("main.requests.post", return_value=FakeResponse()), patch("main._make_gemini_image", return_value="gemini-image-data") as gemini_mock:
                result = _make_image("forest scene", "storybook", "a fox finds a hidden moon")

        self.assertEqual(result, "gemini-image-data")
        gemini_mock.assert_called_once_with("forest scene", "storybook", "a fox finds a hidden moon")

    def test_hugging_face_prompt_includes_story_topic(self):
        with patch.dict("os.environ", {"HF_TOKEN": "test-token", "HF_IMAGE_MODEL": "test/model"}, clear=False):
            class FakeResponse:
                headers = {"content-type": "image/png"}
                content = b"fake-image"

                def raise_for_status(self):
                    pass

            with patch("main.requests.post", return_value=FakeResponse()) as post:
                _make_image("fox beneath glowing trees", "storybook", "a fox finds a hidden moon")

        prompt = post.call_args.kwargs["json"]["inputs"]
        self.assertIn("a fox finds a hidden moon", prompt)
        self.assertIn("fox beneath glowing trees", prompt)


if __name__ == "__main__":
    unittest.main()
