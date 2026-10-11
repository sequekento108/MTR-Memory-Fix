package org.mtr.model;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.blaze3d.vertex.VertexConsumer;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.renderer.texture.OverlayTexture;
import org.joml.Vector2f;
import org.joml.Vector3f;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;

import java.awt.Color;

public record StoredVertexData(float x, float y, float z, Color color, float u, float v, float normalX, float normalY, float normalZ) {

	private static final Color WHITE = Color.WHITE;

	public StoredVertexData modify(double x, double y, double z, boolean mirror) {
		final float multiplier = mirror ? -1 : 1;
		return new StoredVertexData(x() * multiplier + (float) x, y() + (float) y, z() * multiplier + (float) z, color(), u(), v(), normalX() * multiplier, normalY(), normalZ() * multiplier);
	}

	public static void write(ModelPart modelPart, ObjectArrayList<StoredVertexData> storedVertexDataList) {
		final StoredVertexConsumer storedVertexConsumer = new StoredVertexConsumer();
		modelPart.render(new PoseStack(), storedVertexConsumer, 15728816, OverlayTexture.NO_OVERLAY);
		for (int i = 0; i < storedVertexConsumer.vertexEntries.size(); i++) {
			final Vector3f vertex = storedVertexConsumer.vertexEntries.get(i);
			final Vector2f texture = storedVertexConsumer.textureEntries.get(i);
			final Vector3f normal = storedVertexConsumer.normalEntries.get(i);
			storedVertexDataList.add(new StoredVertexData(vertex.x, -vertex.y, -vertex.z, WHITE, texture.x, texture.y, normal.x, -normal.y, -normal.z));
		}
	}

	public static void apply(ObjectArrayList<StoredVertexData> storedVertexDataList, VertexConsumer vertexConsumer) {
		storedVertexDataList.forEach(storedVertexData -> vertexConsumer.addVertex(storedVertexData.x(), storedVertexData.y(), storedVertexData.z(), storedVertexData.color().getRGB(), storedVertexData.u(), storedVertexData.v(), OverlayTexture.NO_OVERLAY, 15728880, storedVertexData.normalX(), storedVertexData.normalY(), storedVertexData.normalZ()));
	}

	static class StoredVertexConsumer implements VertexConsumer {

		private final ObjectArrayList<Vector3f> vertexEntries = new ObjectArrayList<>();
		private final ObjectArrayList<Vector2f> textureEntries = new ObjectArrayList<>();
		private final ObjectArrayList<Vector3f> normalEntries = new ObjectArrayList<>();

		@Override
		public VertexConsumer addVertex(float x, float y, float z) {
			vertexEntries.add(new Vector3f(x, y, z));
			return this;
		}

		@Override
		public VertexConsumer setColor(int red, int green, int blue, int alpha) {
			return this;
		}

		@Override
		public VertexConsumer setUv(float u, float v) {
			textureEntries.add(new Vector2f(u, v));
			return this;
		}

		@Override
		public VertexConsumer setUv1(int u, int v) {
			return this;
		}

		@Override
		public VertexConsumer setUv2(int u, int v) {
			return this;
		}

		@Override
		public VertexConsumer setNormal(float x, float y, float z) {
			normalEntries.add(new Vector3f(x, y, z));
			return this;
		}
	}
}
